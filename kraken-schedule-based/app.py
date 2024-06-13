'''
Automates informed cryptocurrency trading- built around Kraken and Coinmarket API. This code is designed to be run on a 
schedule in aws Lambda. Execution first accesses your Kraken Account's current order ledger and runs 
different set of functions based on the most recent order type. 
If order type is Sell with status Filled: Runs potential buy sequence- Accesses crypto price history via 
CoinMarket Api and logic to determine if any
symbols would be considered optimal entry points at the current time. Then executes via Kraken API if any are found to be optimal
If order type is Buy with status filled: Runs Limit Sell sequence on order id and purchased volume.
If order type is Sell and Open: Will wait a certain number of executions before executing edit order sequence which lowers
the sell target price. This execution number is stored in SSM parameter store.
If order type is Buy and open: Will wait a certain number of executions before executing a new buy sequence.

'''
import boto3
import requests
import json
import traceback
import os
import urllib.parse
import hashlib
import hmac
import base64
import time
from botocore.exceptions import ClientError


def lambda_handler(event, context):
    print(event)
    if 'mocktest' in event:
        print('Pipeline execution mock test here')
        return 'As you were..'
    else:
        pass
    #setting global env vars- some for ease of modifying
    global modifier_limit_loss
    modifier_limit_loss = .998
    global modifier_limit_gain
    modifier_limit_gain = 1.0075
    global coinmarket_key
    coinmarket_key = os.environ['coinmarket_key']
    global topicarn
    topicarn = os.environ['topicarn']
    global api_key
    api_key = os.environ['api_key']  
    global api_sec
    api_sec = os.environ['api_sec']
    global api_url
    api_url = "https://api.kraken.com"
    if event['Interval_Sched'] == 30:
        buy_cycle_threshold = 2
        sell_cycle_threshold = 10
    elif event['Interval_Sched'] == 20:
        buy_cycle_threshold = 3
        sell_cycle_threshold = 15
    #START Main app flow
    main_responses = []
    try:
        order_details = Check_Orders()
        main_responses.append({'Check_Orders': order_details})
        if order_details['status'] == 'open':
            #if found order is open and a sell order- wait x cycles before editing the order for even trade and reset tally
            if order_details['type'] == 'sell':
                time = Check_Cycles_Since_Sell()
                main_responses.append({'Check_Cycles_Since_Sell': time})
                if time >= sell_cycle_threshold:
                    edit = Edit_Limit_Sell(order_details)
                    main_responses.append({'Edit_Limit_Sell':edit})
                    
                    update = Update_Cycles_Since_Sell('reset')
                    main_responses.append({'Update_Cycles_Since_Sell':update})
                else:
                    update=Update_Cycles_Since_Sell('add')
                    main_responses.append({'Update_Cycles_Since_Sell': update})
            #if found order is open and a buy order- wait x cycles before cancelling and creating a new order on the optimal symbol
            elif order_details['type'] == 'buy':
                time = Check_Cycles_Since_Buy()
                main_responses.append({'Check_Cycles_Since_Buy':time})
                if time >= buy_cycle_threshold:
                    cancel= Cancel_Order(order_details)
                    main_responses.append({'Cancel_Order':cancel})
                    
                    prices = Get_Prices()
                    main_responses.append({'Get_Prices':len(prices)})
                    
                    opt_symb = Calculate_Optimal(prices,order_details)
                    main_responses.append({'Calculate_Optimal':opt_symb})
                    
                    buy = Limit_Buy(prices,opt_symb)
                    main_responses.append({'Limit_Buy':buy})
                    
                    update =Update_Cycles_Since_Buy('reset')
                    main_responses.append({'Update_Cycles_Since_Buy':update })
                else:
                    update = Update_Cycles_Since_Buy('add')
                    main_responses.append({'Update_Cycles_Since_Buy':update })
        elif order_details['status'] == 'filled':
            #if found order is filled and a sell then create a limit buy on optimal symbol and
            if order_details['type'] == 'sell':
                prices = Get_Prices()
                main_responses.append({'Get_Prices':len(prices)})
                
                opt_symb = Calculate_Optimal(prices,order_details)
                main_responses.append({'Calculate_Optimal':opt_symb})
                
                buy = Limit_Buy(prices,opt_symb)
                main_responses.append({'Limit_Buy':buy})
                
                update =Update_Cycles_Since_Buy('reset')
                main_responses.append({'Update_Cycles_Since_Buy':update})
            #if found order is filled and buy then create sell order and reset sell tally
            elif order_details['type'] == 'buy':
                sell=Limit_Sell(order_details)
                main_responses.append({'Limit_Sell':sell})
                
                update=Update_Cycles_Since_Sell('reset')
                main_responses.append({'Update_Cycles_Since_Sell':update})
        Sns_Notif_Send(main_responses)
    except Exception as e:
        print("An error occurred:", e)
        Sns_Notif_Send(main_responses)
        traceback.print_exc()



def Check_Orders():
    #open order check
    try:
        print('Checking order ledger')
        uri_path = '/0/private/OpenOrders'
        headers = {}
        headers['API-Key'] = api_key  
        data =  {
            "nonce": str(int(1000*time.time())),
            "trades": True
        }
        headers['API-Sign'] = get_kraken_signature(uri_path,data)
        raw_resp = requests.post((api_url + uri_path), headers=headers, data=data)
        response = raw_resp.json()
        if response['result']['open'] != {}:
            print('open order: ')
            order_id = list(response['result']['open'].keys())[0]
            order_details = {}
            order_details['status'] = 'open'
            order_details['order_id'] = order_id
            order_details['symbol'] = response['result']['open'][order_id]['descr']['pair']
            order_details['type'] = response['result']['open'][order_id]['descr']['type']
            order_details['price'] = float(response['result']['open'][order_id]['descr']['price'])
            order_details['volume'] = float(response['result']['open'][order_id]['vol'])
        else:
            uri_path = '/0/private/ClosedOrders'
            headers = {}
            headers['API-Key'] = api_key
            data =  {
                "nonce": str(int(1000*time.time())),
                "trades": True
            }
            headers['API-Sign'] = get_kraken_signature(uri_path,data)
            raw_resp = requests.post((api_url + uri_path), headers=headers, data=data)
            response = raw_resp.json()
            print('closed order: ')
            order_id = list(response['result']['closed'].keys())[0]
            order_details = {}
            order_details['status'] = 'filled'
            order_details['order_id'] = order_id
            order_details['symbol'] = response['result']['closed'][order_id]['descr']['pair']
            order_details['type'] = response['result']['closed'][order_id]['descr']['type']
            order_details['price'] = float(response['result']['closed'][order_id]['price'])
            order_details['volume'] = float(response['result']['closed'][order_id]['vol'])
        print(order_details)
        return order_details
    except Exception as e:
        print("An error occurred:", e)
        traceback.print_exc()
        return 'failed'
        


#Recieves crypto model and returns a symbol alone
#[{'symbol': 'ADA', 'percent_change_1h': -0.98628824, 'percent_change_24h': 4.7808734, 'percent_change_7d': 13.96633944},
def Calculate_Optimal(prices_perc,order_details):
    try:
        print('determining symbol')
        symbol_price_ratings = []
        '''
        #First Algorythm prioritizes price decreases across all spans-
        #weighted on the following basis: 100- 7d- 4*24h- 2*1h
        for x in prices_perc:
            rating = 100
            
            sevend_rating = x['percent_change_7d']
            rating = rating - sevend_rating
            
            oneh_rating = round(x['percent_change_1h']*2,3)
            rating = rating - oneh_rating

            twentyfourh_rating = round(x['percent_change_24h']*2,3)
            rating = rating - twentyfourh_rating
            
            temp_dict = {'symbol': x['symbol'],'rating': rating}
            symbol_price_ratings.append(temp_dict)
        '''
        #Second algorithm prioritizes stable price through 7d and 24h with a negative 2* weight on 1h change-
        #This simply excludes more consistently descreasing priced symbols
        for x in prices_perc:
            rating = 100
            
            sevend_rating = round(abs(x['percent_change_7d'])*1,4)
            rating = rating - sevend_rating
            
            twentyfourh_rating = round(x['percent_change_24h']*2,4)
            rating = rating - twentyfourh_rating
            
            oneh_rating = round(x['percent_change_1h']*4,4)      
            rating = rating - oneh_rating
            
            temp_dict = {'symbol': x['symbol'],'rating': rating}
            symbol_price_ratings.append(temp_dict)
        
        print('finished with rating algorithm: ')
        sorted_symbol_ratings = sorted(symbol_price_ratings, key=lambda x: x['rating'], reverse=True)  
        print(sorted_symbol_ratings)
        totaled = 0
        for x in sorted_symbol_ratings:
            totaled = totaled+ x['rating']
        avg = round(totaled/len(sorted_symbol_ratings),5)
        print(avg)
        highest_rating_dict = sorted_symbol_ratings[0]
        #Post rating filtering logic
        if highest_rating_dict['rating'] <= 99.9 and avg <= 98.9:
            highest_rated_symbol = 'Market not meeting minimums'        
        else:
            highest_rated_symbol = sorted_symbol_ratings[0]['symbol']
            if highest_rated_symbol == order_details['symbol'].replace('USD',''):
                selected_symbol = sorted_symbol_ratings[1]['symbol']
                print('backup symbol chosen')
            else:
                selected_symbol = sorted_symbol_ratings[0]['symbol']
        print(selected_symbol)
        return selected_symbol
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e)
        return 'failed'



#Runs if
def Cancel_Order(order_details):
    print('Cancelling order to try a new symbol')
    try:
        data = {
            "nonce": str(int(1000*time.time())),
            "txid": order_details['order_id']
        }
        uri_path = '/0/private/CancelOrder'
        headers = {}
        headers['API-Key'] = api_key
        headers['API-Sign'] = get_kraken_signature(uri_path, data)             
        req = requests.post((api_url + uri_path), headers=headers, data=data)
        response = req.json()
        print('canceled order on'+ order_details['symbol'])
        return response
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e)
        return 'failed'



def Edit_Limit_Sell(order_details):
    print('Create limit sell update for loss or less')
    try:
        decimal = Get_Price_Decimal(order_details['symbol'].replace('USD', ''))
        #create new sell order that will decrease in acceptable price
        new_price = round(order_details['price']*modifier_limit_loss,decimal)
        uri_path = '/0/private/EditOrder'
        data = {
            "nonce": str(int(1000*time.time())),
            "txid": order_details['order_id'],
            "volume": order_details['volume'],
            "pair": order_details['symbol'],
            "price": new_price,
        }
        headers = {}
        headers['API-Key'] = api_key
        headers['API-Sign'] = get_kraken_signature(uri_path, data)             
        req = requests.post((api_url + uri_path), headers=headers, data=data)
        response = req.json()
        data = response['result']['descr']
        print(data)
        return data
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e)
        return 'failed'



#runs when buy order is found with filled status uses vol and price data from order details
def Limit_Sell(order_details):
    print('Creating limit sell order max gainer')
    try:
        decimal = Get_Price_Decimal(order_details['symbol'].replace('USD', ''))
        new_price = float(round(order_details['price']*modifier_limit_gain,decimal))
        pair = order_details['symbol']
        data = {
            "nonce": str(int(1000*time.time())),
            "ordertype": "limit",
            "type": "sell",
            "volume": order_details['volume'],
            "pair": pair,
            "price": new_price
        }
        uri_path = '/0/private/AddOrder'
        headers = {}
        headers['API-Key'] = api_key
        headers['API-Sign'] = get_kraken_signature(uri_path, data)               
        raw_response = requests.post((api_url + uri_path), headers=headers, data=data)
        response = raw_response.json()
        print(response)
        data = response['result']['descr']
        return data
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e)
        return 'failed'



# will run on the two buy conditions: open+buy+cylces and closed+sell
def Limit_Buy(prices, opt_symb):
    try:
        print(opt_symb)
        amt = 2350
        for x in prices:
            if x['symbol'] == opt_symb:
                print('optimal symbol info: ')
                print(x)
                current_price = x['current_price']
                break
        #should return decimal places for both volume and price on symbol
        price_decimal = Get_Price_Decimal(opt_symb)
        vol_decimal = Get_Vol_Decimal(opt_symb)
        #create new lower buy limit price
        limit_price = round(current_price*.999,price_decimal)
        volume = round(amt/limit_price,vol_decimal)
        pair = opt_symb+ 'USD'
        uri_path = '/0/private/AddOrder'
        headers = {}
        headers['API-Key'] = api_key
        data = {
            "nonce": str(int(1000*time.time())),
            "ordertype": "limit",
            "type": "buy",
            "volume": volume,
            "pair": pair,
            "price": limit_price
        }
        # get_kraken_signature() as defined in the 'Authentication' section
        headers['API-Sign'] = get_kraken_signature(uri_path, data)             
        raw_response = requests.post((api_url + uri_path), headers=headers, data=data)
        response = raw_response.json()
        print(response)
        data = response['result']['descr']
        print(data)
        return data
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e) 
        return 'failed'



def get_kraken_signature(uri_path, data):
    try:
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = uri_path.encode() + hashlib.sha256(encoded).digest()
        mac = hmac.new(base64.b64decode(api_sec), message, hashlib.sha512)
        sigdigest = base64.b64encode(mac.digest())
        return sigdigest.decode()
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e)
        return 'failed'



def Get_Prices():
    try:
        #Api key and url for coinmarketcap deafult endpoints
        url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
        params = {
            'start': 1,
            'limit': 130,
            'convert': 'USD',
            'sort': 'symbol',
            "market_cap_min": 500000000
        }
        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': coinmarket_key
        }
        raw_response = requests.get(url, params=params, headers=headers)
        response = raw_response.json()
        inclusion_list = ['EOS','UNI','ATOM','TIA','ALGO','SOL','AVAX','MASK','LTC','LINK','DASH','DOT','OP','SUSHI','OMG','XRP','ENJ','BAT','LRC','XLM','AXS','MATIC','ADA','FIL']
        print('total # of currencies in response:')
        print(len(response['data']))
        changes_list = []
        for x in response['data']:        
            #creates dicts list of only whitelisted symbols
            if x['symbol'] in inclusion_list:
                temp_dict = {
                    'symbol': x['symbol'],
                    'current_price': x['quote']['USD']['price'],
                    'percent_change_1h': x['quote']['USD']['percent_change_1h'],
                    'percent_change_24h': x['quote']['USD']['percent_change_24h'],
                    'percent_change_7d': x['quote']['USD']['percent_change_7d']
                }
                changes_list.append(temp_dict)
            else:
                pass
        print('Parsed price info into list of dicts containing each symbols perc change and current price')
        return changes_list
    except Exception as e:
        traceback.print_exc()
        print("An error occurred:", e)
        return 'failed'



#SSM PARAMETER SECTION
def Check_Cycles_Since_Buy():
    print('Get tally ssm parameter since buy in cycles')
    try:
        ssmclient = boto3.client('ssm')
        response = ssmclient.get_parameter(
            Name = 'krakenbuycyclecount'
        )
        cycles = int(response['Parameter']['Value'])
        return cycles
    except ClientError as e:
        print('Client error: %s' % e)
        return 'failed'

def Update_Cycles_Since_Buy(cmd):
    print('Get and update tally buy parameter')
    try:
        ssmclient = boto3.client('ssm')
        response = ssmclient.get_parameter(
            Name = 'krakenbuycyclecount'
        )
        cycles = int(response['Parameter']['Value'])
        if cmd == 'add':
            new_cycles_count = cycles+1
        elif cmd == 'reset':
            new_cycles_count = 0
        #Update with new
        response = ssmclient.put_parameter(
            Name = 'krakenbuycyclecount',
            Value = json.dumps(new_cycles_count),
            Type = 'String',
            Overwrite = True
        )
        print('updated buy cycles: '+json.dumps(new_cycles_count))
        return 'updated buy cycles: '+json.dumps(new_cycles_count)
    except ClientError as e:
        print('Client error: %s' % e)
        return 'failed'


def Check_Cycles_Since_Sell():
    print('Get tally ssm parameter since sell in cycles')
    try:
        ssmclient = boto3.client('ssm')
        response = ssmclient.get_parameter(
            Name = 'krakensellcyclecount'
        )
        cycles = int(response['Parameter']['Value'])
        print('current sell cycles: '+json.dumps(cycles))
        return cycles
    except ClientError as e:
        print('Client error: %s' % e)
        return 'failed'

def Update_Cycles_Since_Sell(cmd):
    try:
        print('get and update sell cycles')
        ssmclient = boto3.client('ssm')
        response = ssmclient.get_parameter(
            Name = 'krakensellcyclecount'
        )
        cycles = int(response['Parameter']['Value'])
        if cmd == 'add':
            new_cycles_count = cycles+1
        elif cmd == 'reset':
            new_cycles_count = 0
        response = ssmclient.put_parameter(
                Name = 'krakensellcyclecount',
                Value = json.dumps(new_cycles_count),
                Type = 'String',
                Overwrite = True
            )
        print('updated sell cycles: '+ json.dumps(new_cycles_count))
        return 'updated sell cycles: '+ json.dumps(new_cycles_count)
    except ClientError as e:
        print('Client error: %s' % e)
        return 'failed'
#END SSM PARAMETER SECTION



def Sns_Notif_Send(body):
    snsclient = boto3.client('sns')
    try:
        response = snsclient.publish(
            TopicArn = topicarn, 
            Message = json.dumps(body)  
        )
        print('sent sns')
    except Exception as e:
        print("An error occurred:", e)
        print('died at sns')



#GET DEC SECTION
def Get_Price_Decimal(symbol):
    try:   
        crypto_decimals_price = {
            'EOS': 4, 'UNI': 3, 'ATOM': 4, 'TIA': 4, 'ALGO': 5 , 'SOL': 2, 
            'AVAX': 2, 'MASK': 3, 'LTC': 2, 'LINK': 5, 'DASH': 3, 'DOT': 4, 'OP': 4, 
            'SUSHI': 3, 'OMG': 6, 'XRP': 5, 'ENJ': 3, 'BAT': 5, 'LRC': 4, 'XLM': 5, 'AXS': 3, 
            'MATIC': 4, 'ADA': 5, 'FIL': 3
        }
        data = crypto_decimals_price[symbol]
    except Exception as e:
        print("An error occurred:", e)
        print('There was likely a symbol error in get_price_decimal')
        data = 0
    return data

def Get_Vol_Decimal(symbol):
    try:   
        crypto_decimals_vol = {
            'EOS': 7, 'UNI': 7, 'ATOM': 7, 'TIA': 5, 'ALGO':7 , 'SOL': 7, 
            'AVAX': 7, 'MASK': 7, 'LTC': 7, 'LINK': 7, 'DASH': 7, 'DOT': 7, 'OP': 5, 
            'SUSHI': 7, 'OMG': 7, 'XRP': 7, 'ENJ': 7, 'BAT': 7, 'LRC': 6, 'XLM': 7, 'AXS': 7, 
            'MATIC': 7, 'ADA': 7, 'FIL': 7
        }
        data = crypto_decimals_vol[symbol]
    except Exception as e:
        print("An error occurred:", e)
        print('There was likely a symbol error in get_Vol_decimal')
        data = 0
    return data
#END GET DEC SECTION

'''
event = {
    'queryStringParameters': {
        'mock': ''
    },
    'body': ''
}
context = ''

lambda_handler(event, context)
'''
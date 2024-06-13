#Part of a system of functions for managing incoming and outgoing gaming accounts details for 
# automating the storage and fulfilment flow.
# Upload Account
import boto3
import json
import os
from botocore.exceptions import ClientError
s3client = boto3.client('s3')
#create a body request in postman containing body 
#in this format for manual boosted accounts

def lambda_handler(event, context):
    #Accessing bucket name from this Lambda's environment variables
    env_variables = os.environ
    bkt_name = env_variables['userbucket'].strip()
    print(type(event['body']))
    try:
        main_data = json.loads(event['body'])
        if main_data['event'] == 'accountFinished' and main_data['secret'] =='test':
            print(main_data)
            region = main_data['data']['region'].lower()
            if main_data['data']['blueEssence'] >= 40000 and main_data['data']['blueEssence'] <= 50000:
                types = '40'
            elif main_data['data']['blueEssence'] >= 50000 and main_data['data']['blueEssence']<= 100000:
                types = '60'
            elif main_data['data']['blueEssence'] >= 100000:
                types = '100'
            else:
                types = '40'
            if main_data['data']['level'] =='enhanced':
                tier = 'enhanced'
            else:
                tier = 'regular'
            u = main_data['data']['username']
            p = main_data['data']['password']
            billnye = {}
            billnye[u] = p
            
            acc_data = {}
            acc_data['region'] = region
            acc_data['type'] = types
            acc_data['tier'] = tier
            acc_data['details'] = billnye
            print(acc_data)
        else:
            print('unrecognized event')

        main_resp = Update_List(bkt_name,acc_data)
            
        
    except:
        print('Failed at parsing new account event')   
        main_resp = 'Failed at parsing new account event'
    main_response_object = {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(main_resp)
        }
    return main_response_object


def Update_List(bkt_name,acc_data):
    acc_region = acc_data['region']
    acc_type = acc_data['type']
    acc_tier = acc_data['tier']
    acc_details = acc_data['details']
    keys = 'accountsdata/' + acc_region + '.json'
    
    try:
        response = s3client.get_object(
            Bucket = bkt_name,
            Key = keys
        )
        print('get_object for existing accs successful')
        response_body = json.loads(response['Body'].read().decode('utf-8'))
        response_body['accounts'][acc_type][acc_tier].append(acc_details)
        reupload_list = json.dumps(response_body)
        response = s3client.put_object(
            Bucket = bkt_name,
            Key = keys,
            Body = reupload_list
        )
        msg = 'added account to list'
        print(msg)    
    except ClientError as e:
        msg = 'failed to update list'
        print(msg)
        print('Client error: %s' % e)
    return msg

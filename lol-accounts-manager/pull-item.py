#Part of a system of functions for managing incoming and outgoing gaming accounts details for 
# automating the storage and fulfilment flow.
#Get account
import boto3
import json
import random
import os
from botocore.exceptions import ClientError
s3client = boto3.client('s3')



def lambda_handler(event, context):
    #Accessing bucket name from this Lambda's environment variables
    env_variables = os.environ
    #parsing request data
    account_region = event['queryStringParameters']['account_region'].strip().lower()
    account_type = event['queryStringParameters']['account_type'].strip()
    account_tier = event['queryStringParameters']['account_tier'].strip()
    transaction_id = event['queryStringParameters']['transaction_id'].strip()
    user = event['queryStringParameters']['user'].strip()
    #Creating dict for uploads
    request_data = {}
    request_data['account_region'] = account_region
    request_data['account_type'] = account_type
    request_data['account_tier'] = account_tier
    request_data['user'] = user 
    request_data['transaction_id'] = transaction_id

    request_data['ses_arn'] = env_variables['sesarn'].strip()
    request_data['bkt_name'] = env_variables['userbucket'].strip()
    request_data['table_name'] = env_variables['usertable'].strip()
    sel_acc = Get_Account(request_data)
    if sel_acc != 0:
        write_status = DB_Write(request_data,sel_acc)
        if write_status != 0:
            ses_status = Send(request_data,sel_acc)
            if ses_status != 0:
                main_response_object = sel_acc
            else:
                main_response_object = 'failed to send email'
        else:
            main_response_object = 'failed to update db'
    else:
        main_response_object = 'failed to get account'
    
    #Main response 
    main_response_object = {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': main_response_object
    }
    return main_response_object #end
                    
            

def Get_Account(request_data):
    acc_region = request_data['account_region']
    acc_type = request_data['account_type']
    acc_tier = request_data['account_tier']
    keys = 'accountsdata/' + acc_region + '.json'
    try:
        response = s3client.get_object(
            Bucket = request_data['bkt_name'],
            Key = keys
        )
        print('get_object for accs successful')
        response_body = json.loads(response['Body'].read().decode('utf-8'))
        account = response_body['accounts'][acc_type][acc_tier].pop(0)
        
        reupload_list = json.dumps(response_body)
        response = s3client.put_object(
            Bucket = request_data['bkt_name'],
            Key = keys,
            Body = reupload_list
        )
        json_account = json.dumps(account)
        print(json_account)
        print('put update on list successful')    
        return json_account
    except ClientError as e:
        print('Client error: %s' % e)
        return 0


def DB_Write(request_data, account_key):
    dbclient = boto3.client('dynamodb')
    if request_data['account_tier'] == 'regular':
        try:
            response = dbclient.put_item(
                TableName = request_data['table_name'],
                Item = {
                    'name': {'S': request_data['account_type']},
                    'id': {'S': request_data['transaction_id']},
                    'user': {'S': request_data['user']},
                    'itempath': {'S': account_key}
                }
            )
            print('Database updated..')
            data = 1
        except ClientError as e:
            print('Client error: %s' % e)
            data = 0
    else:
        data = 1 
    return data

def Send(request_data, account_data):
    sesclient = boto3.client('ses')
    try:
        response = sesclient.send_email(
            Source = 'pjcrollo@gmail.com',
            Destination = {
                "ToAddresses": [request_data['user']]
            },
            SourceArn = request_data['ses_arn'],
            Message = {
                'Subject': {
                    'Data': 'Braum Is Here!.. your purchased account',
                },
                'Body': {
                    'Text': {
                        'Data': account_data
                    }
                }
            }
        )
        print('sent account info to user email')
    except ClientError as e:
        print('Client error: %s' % e)
        return 0 
    



#event = {
#    'queryStringParameters': {
#        'account_region': 'na',
#        'account_type': '40',
#        'account_tier': 'regular',
#        'transaction_id': '111111111',
#        'user': 'polkiju'
#    }
#}
#context = ''
#lambda_handler(event, context)

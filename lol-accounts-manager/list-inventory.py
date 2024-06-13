#Part of a system of functions for managing incoming and outgoing gaming accounts details for 
# automating the storage and fulfilment flow.
#List account
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
    region = event['queryStringParameters']['region']
    main_resp = List_Inv(bkt_name, region)
            
    
    
    main_response_object = {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(main_resp)
        }
    return main_response_object


def List_Inv(bkt_name,region):
    keys = 'accountsdata/' + region + '.json'
    
    try:
        response = s3client.get_object(
            Bucket = bkt_name,
            Key = keys
        )
        print('get_object for listing existing accs successful')
        
        response_body = json.loads(response['Body'].read().decode('utf-8'))
        fourtyreg = len(response_body['accounts']['40']['regular'])
        fourtyenh = len(response_body['accounts']['40']['enhanced'])
        sixtyreg = len(response_body['accounts']['60']['regular'])
        sixtyenh = len(response_body['accounts']['60']['enhanced'])
        hundredreg = len(response_body['accounts']['100']['regular'])
        hundredenh = len(response_body['accounts']['100']['enhanced'])
        
        
        data = {
            'accounts': {
                '40': {
                    'regular':fourtyreg,
                    'enhanced':fourtyenh
                },
                '60': {
                    'regular':sixtyreg,
                    'enhanced':sixtyenh
                },
                '100': {
                    'regular':hundredreg,
                    'enhanced':hundredenh
                } 
            }
        }
        
    except ClientError as e:
        print('Client error: %s' % e)
        data = 'err'
    return data

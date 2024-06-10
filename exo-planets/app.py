import boto3
import json
import requests
from datetime import datetime 

def lambda_handler(event):
    bDate = event['queryStringParameters']['bDate']
    if ((bDate[2] != '/') or (bDate[5] !='/')):
        result = "ERR: check date format"

    
    else:
        month = float(bDate[:2])
        day = float(bDate[3:5])
        year = float(bDate[6:])
        monthQuantified = month/12
        dayQuantified = day/3000
        QuantifiedbDay = year + monthQuantified + dayQuantified
        dt = json.dumps(datetime.now().isoformat(timespec='hours'))
        nowyear = float(dt[1:5])
        nowmonth = float(dt[6:8])
        nowday = float(dt[9:11])
    
        nowmonthQuantified = nowmonth/12
        nowdayQuantified = nowday/3000
        QuantifiedCurrentDay = nowyear + nowmonthQuantified + nowdayQuantified
        age = QuantifiedCurrentDay - QuantifiedbDay
    
        parsecyear = 0.306601
        resultparsecs = round(age*parsecyear, 5)
        #CONSTRUCT RESPONSE BACK TO api gateway/app.js
        responseobj = {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(Get_System(resultparsecs))
        }
        result = responseobj

    return result
    

#sends parameters to archive db via api endpoint
def Get_System(parsecs):
    minparsecs = json.dumps(parsecs*.92)
    parsecs = json.dumps(parsecs)
    ept = 'https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=\
select+pl_name+from+ps+where+sy_dist+between+'+minparsecs+'+and+'+parsecs+'+order+by+sy_dist+desc'+'&format=json'

    response = requests.get(ept)
    exoresults = response.json()
    #Return dict of planet name and maybe other attr
    data = exoresults[0]['pl_name']
    print(data)
    return data  


#sample event
#event = {'queryStringParameters': {'bDate': '09/09/1999'}} 
#lambda_handler(event)


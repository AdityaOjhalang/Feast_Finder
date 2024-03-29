import boto3
import json
import random
import requests
import logging


# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs_client = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')
es_client = boto3.client('es')
ses_client = boto3.client('ses')

def lambda_handler(event, context):


    queue_url = 'https://sqs.us-east-1.amazonaws.com/471112913653/Q1'
    ids = []
    sqs_response = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        MessageAttributeNames=['All']
    )

    if 'Messages' in sqs_response:
        message = sqs_response["Messages"][0]
        receipt_handle = message['ReceiptHandle']

        if 'MessageAttributes' in message:
            message_attributes = message['MessageAttributes']
            cuisine_type = message_attributes['Cuisine']['StringValue'] if 'Cuisine' in message_attributes else None
            location = message_attributes['Location']['StringValue'] if 'Location' in message_attributes else None
            email = message_attributes['email']['StringValue'] if 'Email' in message_attributes else None
            num_people = message_attributes['NumberOfPeople'][
                'StringValue'] if 'NumberOfPeople' in message_attributes else None
            date = message_attributes['DiningDate']['StringValue'] if 'DiningDate' in message_attributes else None
            time = message_attributes['DiningTime']['StringValue'] if 'DiningTime' in message_attributes else None

            user_details = {
                'Location': 'Manhattan',
                'Cuisine': cuisine_type,
                'Number_people': num_people,
                'Date': date,
                'Time': time
            }
        print(cuisine_type, "===============")
        es_response = es_query_for_cuisine(es_client, cuisine_type)
        print("=============== ES ================ : ",es_response)
        if len(es_response) > 0:
            ids = random.sample(es_response, 3)
        
        restaurants = []
        
        for id in ids:
                restaurant_info = fetch_restaurant_info(dynamodb, id)
                if restaurant_info:
                    # Log the restaurant info to check the contents
                    logger.info(f"Restaurant info fetched: {restaurant_info}")
                else:
                    # Log a warning if no info was fetched
                    logger.warning(f"No restaurant info found for ID: {id}")
                restaurants.append(restaurant_info)
        
        
        email_rev = 'ao2612@nyu.edu'
        prev_location = 'Manhattan'
        email_body = format_email_body(restaurants, user_details)
        
        success = save_previous_recommendation(email_rev, prev_location, cuisine_type,email_body)
        if success:
            print("++++++++++++++++ PREV RECOMMENDS ADDED +++++++++++++++++++++++")
        else:
            print("++++++++++++++++ FAILEDDDD PREV RECOMMENDS ADDED +++++++++++++++++++++++")
            
        email_body = format_email_body(restaurants, user_details)
        
        send_email(ses_client, 'ao2612@nyu.edu', email_body)

        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

        message = {
            'message': 'Email sent succesfully'
        }

        return {

            'statusCode': 200,
            'body': json.dumps(message)
        }

    else:
        return {
            'statusCode': 200,
            'body': json.dumps('No message in queue')
        }
    


def save_previous_recommendation(email, location, cuisine,restaurants):
    try:
        table_name = 'previous-records'
        table = dynamodb.Table(table_name)
        
        response = table.put_item(
            Item={
                'email': email,
                'location': location,
                'cuisine': cuisine,
                'restaurants':restaurants
            }
        )
        
        return True
        
    except Exception as e:
        print(e)
        return False

def es_query_for_cuisine(es_client, cuisine_type):
    es_url = 'https://search-restaurants-data-7j66miiviawwaa66vq656aqpia.aos.us-east-1.on.aws/restaurants/_search'
    headers = {'Content-Type': 'application/json'}
    auth = ('***', '******') # Replace with your ES credentials
    query = {
        "query": {
            "match": {
                "cuisine": cuisine_type
            }
        },  "size":100
    }
    try:
        response = requests.get(es_url, headers=headers, auth=auth, data=json.dumps(query))
        if response.status_code == 200:
            results = response.json()
            print(results['hits']['hits'][0]['_source']['RestaurantID'])
            
            ids = []
            for res in results['hits']['hits']:
                id = res['_source']['RestaurantID']
                ids.append(id)
            return ids
        
    except Exception as e:
        print(e)
    return []

def fetch_restaurant_info(dynamodb, restaurant_id):
    table_name = 'yelp-restaurants'
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(
            Key={'business_id': restaurant_id}
        )

        if 'Item' in response:
            logger.info(f"Item found: {response['Item']}")
            return response['Item']
        else:
            logger.warning(f"No item found with id: {restaurant_id}")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch item from DynamoDB: {str(e)}")
        return None

def format_email_body(restaurants_info, user_details):
    html = """<tr style="background-color: #f2f2f2;">
    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Name</th>
    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Rating</th>
    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Review Count</th>
    <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Address</th>
    """

    for data in restaurants_info:
        address = data['address'].replace("\'", '').replace('[', '').replace(']', '').replace('"', '')

        # Append a row to the table for each JSON object
        html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{data['name']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{data['rating']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{data['number_of_reviews']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{address}</td>
                </tr>
        """

    html_1 = f'''<html><head></head><body><p>Here are the requested suggestions for the following details: <br> Location: {user_details['Location']} <br> 
    Number of people: {user_details['Number_people']} <br>
    Cuisine: {user_details['Cuisine']} <br>
    Date: {user_details['Date']} <br>
    Time: {user_details['Time']} <br>
    </p><p><table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd;">>'''
    html_2 = "</table></p></body></html>"

    print(html_1 + html + html_2)

    return html_1 + html + html_2


def send_email(ses_client, email, email_body):
    sender_email = "aditya.ojha2820@gmail.com"

    subject = "Restaurant Recommendations"

    try:
        response = ses_client.send_email(
            Source=sender_email,
            Destination={
                'ToAddresses': [
                    email
                ]
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': 'Here are your recommendations!',
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': email_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print("Email sent! Message ID:", response['MessageId'])
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
    

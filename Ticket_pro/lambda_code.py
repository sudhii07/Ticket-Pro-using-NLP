import json
import uuid
import boto3
from datetime import datetime

def lambda_handler(event, context): 
    comprehend = boto3.client('comprehend')
    dynamodb = boto3.resource('dynamodb')
    sns = boto3.client('sns')

    table = dynamodb.Table('SupportTickets')

    name = event['name']
    email = event['email']
    category = event['category']  # Updated to accept category
    description = event['description']
    order_id = event.get('order_id', 'N/A')
    

    # Sentiment analysis
    # Sentiment analysis
    sentiment = comprehend.detect_sentiment(Text=description, LanguageCode='en')['Sentiment']
    
    # Key phrases extraction
    phrases = comprehend.detect_key_phrases(Text=description, LanguageCode='en')
    key_phrases = [phrase['Text'] for phrase in phrases['KeyPhrases']]
    
    # Assign priority
    priority = assign_priority(sentiment=sentiment, key_phrases=key_phrases)

    ticket_id = str(uuid.uuid4())

    # Save ticket in DynamoDB
    table.put_item(Item={
        'ticket_id': ticket_id,
        'name': name,
        'email': email,
        'category': category,  # Save category instead of subject
        'description': description,
        'sentiment': sentiment,
        'priority': priority,
        'timestamp': datetime.utcnow().isoformat(),
        'status':'Not Taken',
        'order_id': order_id
    })

    # ✅ Send Email using SNS
    topic_arn = "arn:aws:sns:ap-south-1:575320235149:ticket-alerts"
    message = f"""
New Support Ticket Raised!

Name: {name}
Email: {email}
Category: {category}

Description:
{description}

Priority: {priority}
Sentiment: {sentiment}
"""
    sns.publish(
        TopicArn=topic_arn,
        Subject=f"New Ticket - Priority: {priority}",
        Message=message
    )

    return {
        'status': 'success',
        'priority': priority
    }

# Correct assign_priority function
def assign_priority(sentiment='NEGATIVE', key_phrases=[]):
    critical_keywords = ['urgent', 'failed', 'crash', 'not working', 'error', 'payment']
    if sentiment == 'NEGATIVE' or any(k.lower() in [kp.lower() for kp in key_phrases] for k in critical_keywords):
        return 'High'
    elif sentiment == 'NEUTRAL':
        return 'Medium'
    else:
        return 'Low'

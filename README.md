📌 Project Overview

This system allows customers to submit support requests online. The application processes each request using Amazon Comprehend to detect sentiment and extract key phrases. Based on this analysis, the system automatically assigns a priority level (High, Medium, Low).

The ticket is stored in Amazon DynamoDB, and the support team receives an email notification via AWS SNS whenever a new ticket is created.

🚀 Features

✅ AI-based sentiment analysis for support tickets
✅ Automatic priority assignment
✅ Admin dashboard for ticket monitoring
✅ Email notifications using AWS SNS
✅ Serverless ticket processing with AWS Lambda
✅ Cloud-based storage with DynamoDB
✅ Simple and user-friendly interface

🧠 System Workflow

1️⃣ User submits a support ticket
2️⃣ Request is sent to AWS Lambda
3️⃣ Amazon Comprehend analyzes the message sentiment
4️⃣ System assigns ticket priority automatically
5️⃣ Ticket is stored in DynamoDB
6️⃣ SNS sends an email notification to the support team

🛠️ Technologies Used
Backend

Python

Flask

Cloud & AI Services

AWS Lambda

Amazon Comprehend

Amazon DynamoDB

Amazon SNS

Frontend

HTML

CSS

JavaScript

📂 Project Structure

AI-Support-Ticket-System/

│

├── app.py                 # Flask application for ticket submission

├── admin_panel.py         # Admin dashboard for managing tickets

├── lambda_code.py         # AWS Lambda function for ticket analysis

│

├── templates/             # HTML templates

├── static/                # CSS, JS, images

│

└── README.md

⚙️ Installation Guide

1️⃣ Clone the Repository
git clone https://github.com/sudhii07/Ticket pro using NLP.git
2️⃣ Install Required Packages
pip install flask boto3
3️⃣ Configure AWS Credentials
aws configure

Provide:

AWS Access Key

AWS Secret Key

Region (example: ap-south-1)

4️⃣ Create Required AWS Resources

You must configure:

DynamoDB table: SupportTickets

SNS Topic for notifications

Lambda function for processing tickets

5️⃣ Run the Application
python app.py

Open in browser:

http://localhost:5000
📊 Ticket Priority Logic

The system assigns ticket priority based on sentiment and critical keywords.

Sentiment	Priority
Negative	High
Neutral	Medium
Positive	Low

Critical keywords such as urgent, failed, crash, error, payment automatically increase ticket priority.

📸 Screenshots

(Add screenshots here after uploading them to your repository)

Example:

screenshots/
│
├── homepage.png
├── ticket-form.png
├── admin-dashboard.png

Then display them like:

![Homepage](screenshots/homepage.png)
![Admin Dashboard](screenshots/admin-dashboard.png)
🔮 Future Enhancements

AI chatbot integration

Ticket auto-assignment to support agents

Analytics dashboard

Real-time ticket tracking

Multi-language support

👨‍💻 Author

Sudhan Angadi

🔗 GitHub: https://github.com/sudhii07

🔗 LinkedIn: https://linkedin.com/in/yourprofile

📜 License

This project is created for educational and learning purposes.

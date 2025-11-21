#!/usr/bin/env python3
"""Example script to test sending an email via the SMTP proxy."""
import requests
import time
import sys

# Configuration
API_URL = "http://localhost:8000/api/send"
JWT_TOKEN = "YOUR_JWT_TOKEN_HERE"  # Replace with your actual JWT token

def send_test_email():
    """Send a test email."""

    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json"
    }

    # Email data
    data = {
        "to": ["recipient@example.com"],  # Replace with actual recipient
        "subject": "Test Email from FastAPI SMTP Proxy",
        "content": """
            <html>
                <body>
                    <h1>Hello from FastAPI SMTP Proxy!</h1>
                    <p>This is a test email sent via the SMTP proxy.</p>
                    <p>If you're reading this, it means the proxy is working correctly!</p>
                    <hr>
                    <p><small>Sent at: {}</small></p>
                </body>
            </html>
        """.format(time.strftime("%Y-%m-%d %H:%M:%S")),
        "timestamp": int(time.time()),
        "content_type": "text/html",
        "from": "sender@example.com",  # Optional: will use client default if not provided
        "from_name": "SMTP Proxy Test"  # Optional
    }

    print("Sending test email...")
    print(f"To: {', '.join(data['to'])}")
    print(f"Subject: {data['subject']}")

    try:
        response = requests.post(API_URL, json=data, headers=headers)

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 200:
            print("\n✅ Email sent successfully!")
        else:
            print("\n❌ Failed to send email")

    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to the API. Is the server running?")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)


def send_email_with_attachment():
    """Send a test email with an attachment."""
    import base64

    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json"
    }

    # Create a simple text file as an example attachment
    file_content = "This is a test attachment file.\nCreated by the SMTP proxy test script."
    encoded_content = base64.b64encode(file_content.encode()).decode()

    data = {
        "to": ["recipient@example.com"],
        "subject": "Test Email with Attachment",
        "content": "<h1>Email with Attachment</h1><p>Please find the attached file.</p>",
        "timestamp": int(time.time()),
        "content_type": "text/html",
        "attachments": [
            {
                "filename": "test_attachment.txt",
                "content": encoded_content,
                "content_type": "text/plain"
            }
        ]
    }

    print("Sending test email with attachment...")

    try:
        response = requests.post(API_URL, json=data, headers=headers)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 200:
            print("\n✅ Email with attachment sent successfully!")
        else:
            print("\n❌ Failed to send email")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    if JWT_TOKEN == "YOUR_JWT_TOKEN_HERE":
        print("❌ Error: Please set your JWT_TOKEN in the script before running!")
        print("\nTo get a JWT token:")
        print("1. Run: python manage.py create-api-key")
        print("2. Copy the generated token")
        print("3. Replace 'YOUR_JWT_TOKEN_HERE' in this script")
        sys.exit(1)

    print("FastAPI SMTP Proxy - Test Email Script")
    print("=" * 50)

    # Uncomment the test you want to run:
    send_test_email()
    # send_email_with_attachment()

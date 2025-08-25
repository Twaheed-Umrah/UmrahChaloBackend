import random
from django.core.mail import send_mail
from twilio.rest import Client
from django.conf import settings


def generate_login_otp():
    return str(random.randint(100000, 999999))


def send_email_otp(to_email, otp, purpose="login"):
    subject = f"Your OTP for {purpose.capitalize()}"
    message = f"Your OTP is {otp}. It is valid for 5 minutes."
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email])


def send_sms_otp(to_phone, otp):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=f"Your OTP is {otp}. It is valid for 5 minutes.",
        from_=settings.TWILIO_PHONE_NUMBER,
        to=to_phone
    )
    return message.sid

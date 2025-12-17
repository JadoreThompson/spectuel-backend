from fastapi import APIRouter, BackgroundTasks

from services import EmailService
from config import CUSTOMER_SUPPORT_EMAIL
from .models import ContactForm


router = APIRouter(prefix="/public", tags=["Public"])
email_service = EmailService(sender_name="Support", sender_email="support@domain.com")


@router.get("/healthcheck")
async def healthcheck():
    return {"status": "healthy"}


@router.post("/contact", status_code=202)
async def contact_us(body: ContactForm, background_tasks: BackgroundTasks):
    subject = f"New Contact Inquiry from {body.name}"

    em_body = f"""
You have received a new message from the Gova website contact form.\n

Contact Details:\n
- Name: {body.name}\n
- Email: {body.email}\n

Message:\n
{body.message}
"""
    background_tasks.add_task(
        email_service.send_email,
        recipient=CUSTOMER_SUPPORT_EMAIL,
        subject=subject,
        body=em_body.strip(),
    )

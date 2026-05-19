import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(body, "html"))
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.sendmail(settings.SMTP_USER, to, msg.as_string())
    except Exception as e:
        logger.warning("Email not sent to %s: %s", to, e)


def notify_worker_new_offer(worker_email: str, worker_name: str, order_title: str, address: str) -> None:
    send_email(
        to=worker_email,
        subject="Новое предложение о заказе",
        body=(
            f"<p>Здравствуйте, {worker_name}!</p>"
            f"<p>Вам поступило новое предложение о заказе <b>{order_title}</b> по адресу: {address}.</p>"
            f"<p>Войдите в приложение, чтобы принять или отклонить предложение.</p>"
        ),
    )


def notify_employer_worker_accepted(employer_email: str, order_title: str, worker_name: str) -> None:
    send_email(
        to=employer_email,
        subject="Исполнитель принял ваш заказ",
        body=(
            f"<p>Ваш заказ <b>{order_title}</b> принят исполнителем <b>{worker_name}</b>.</p>"
            f"<p>Ожидайте выполнения.</p>"
        ),
    )


def notify_employer_worker_declined(employer_email: str, order_title: str, next_found: bool) -> None:
    if next_found:
        body = (
            f"<p>Исполнитель отклонил ваш заказ <b>{order_title}</b>.</p>"
            f"<p>Мы нашли следующего ближайшего исполнителя и отправили ему предложение.</p>"
        )
    else:
        body = (
            f"<p>К сожалению, для вашего заказа <b>{order_title}</b> не найдено доступных исполнителей.</p>"
            f"<p>Попробуйте создать заказ позже.</p>"
        )
    send_email(
        to=employer_email,
        subject="Обновление по вашему заказу",
        body=body,
    )


def notify_no_workers(employer_email: str, order_title: str) -> None:
    send_email(
        to=employer_email,
        subject="Нет доступных исполнителей",
        body=(
            f"<p>К сожалению, для вашего заказа <b>{order_title}</b> не найдено доступных исполнителей.</p>"
            f"<p>Попробуйте создать заказ позже.</p>"
        ),
    )


def notify_order_completed(email: str, name: str, order_title: str) -> None:
    send_email(
        to=email,
        subject="Заказ завершён",
        body=(
            f"<p>Здравствуйте, {name}!</p>"
            f"<p>Заказ <b>{order_title}</b> успешно завершён.</p>"
        ),
    )

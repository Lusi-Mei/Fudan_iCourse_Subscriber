"""Email notification via QQ SMTP."""

import smtplib
from collections import OrderedDict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from email.utils import formataddr

from . import config


def _md_to_html(md_text: str) -> str:
    """Convert Markdown to HTML, falling back to <pre> on error."""
    try:
        import markdown

        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except ImportError:
        return f"<pre>{escape(md_text)}</pre>"


class Emailer:
    """Send course summary emails via QQ SMTP SSL."""

    def __init__(self):
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.sender = config.SMTP_EMAIL
        self.password = config.SMTP_PASSWORD
        self.receiver = config.RECEIVER_EMAIL

    def send(self, items: list[dict]):
        """Send a single email containing all lecture summaries.

        Args:
            items: List of dicts, each with keys:
                   course_title, sub_title, date, summary
        """
        if not items:
            return

        # Group by course (preserve insertion order)
        courses: OrderedDict[str, list[dict]] = OrderedDict()
        for item in items:
            courses.setdefault(item["course_title"], []).append(item)

        # Subject: [iCourse] 数据结构 (3), 操作系统 (2)
        parts = [f"{ct} ({len(lecs)})" for ct, lecs in courses.items()]
        subject = f"[iCourse 课程内容更新] {', '.join(parts)}"

        # Plain text
        plain_sections = []
        for course_title, lectures in courses.items():
            plain_sections.append(f"{'=' * 40}")
            plain_sections.append(f"课程：{course_title}")
            plain_sections.append(f"{'=' * 40}")
            for lec in lectures:
                plain_sections.append(
                    f"\n--- {lec['sub_title']} ({lec['date']}) ---\n"
                )
                plain_sections.append(lec["summary"])
        plain = "\n".join(plain_sections)

        # HTML
        html_sections = []
        for course_title, lectures in courses.items():
            html_sections.append(f"<h2>{escape(course_title)}</h2>")
            for lec in lectures:
                html_sections.append(
                    f"<h3>{escape(lec['sub_title'])} "
                    f"<small>({escape(lec['date'])})</small></h3>"
                )
                html_sections.append(_md_to_html(lec["summary"]))
                html_sections.append("<hr>")
        html = "\n".join(html_sections)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr(("iCourse Subscriber", self.sender))
        msg["To"] = self.receiver
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL(self.host, self.port) as server:
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.receiver, msg.as_string())

        print(f"[Emailer] Sent: {subject}")

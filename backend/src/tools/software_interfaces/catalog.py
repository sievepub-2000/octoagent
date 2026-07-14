"""Composio-compatible software interface catalog.

The catalog mirrors Composio's managed Composio toolkit surface so OctoAgent
can present the same broad software-interface vocabulary without hard-coding
each provider as a separate agent tool. Runtime execution is routed through the
software-interface Composio gateway when credentials are configured.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoftwareInterface:
    slug: str
    name: str
    category: str
    description: str
    source: str = "composio_catalog"
    auth_provider: str = "composio"
    status: str = "available"
    supports_oauth: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "id": f"software-interface:{self.slug}",
            "slug": self.slug,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "source": self.source,
            "auth_provider": self.auth_provider,
            "status": self.status,
            "supports_oauth": self.supports_oauth,
        }


COMPOSIO_TOOLKITS: tuple[tuple[str, str], ...] = (
    ("airtable", "Airtable"),
    ("apaleo", "Apaleo"),
    ("asana", "Asana"),
    ("attio", "Attio"),
    ("basecamp", "Basecamp"),
    ("bitbucket", "Bitbucket"),
    ("blackbaud", "Blackbaud"),
    ("boldsign", "Boldsign"),
    ("box", "Box"),
    ("cal", "Cal"),
    ("calendly", "Calendly"),
    ("canva", "Canva"),
    ("capsule_crm", "Capsule CRM"),
    ("clickup", "ClickUp"),
    ("confluence", "Confluence"),
    ("contentful", "Contentful"),
    ("convex", "Convex"),
    ("crowdin", "Crowdin"),
    ("dart", "Dart"),
    ("dialpad", "Dialpad"),
    ("digital_ocean", "DigitalOcean"),
    ("discord", "Discord"),
    ("discordbot", "Discord Bot"),
    ("dropbox", "Dropbox"),
    ("dub", "Dub"),
    ("dynamics365", "Dynamics 365"),
    ("eventbrite", "Eventbrite"),
    ("excel", "Excel"),
    ("exist", "Exist"),
    ("facebook", "Facebook"),
    ("fathom", "Fathom"),
    ("figma", "Figma"),
    ("freeagent", "Freeagent"),
    ("freshbooks", "FreshBooks"),
    ("github", "GitHub"),
    ("gitlab", "GitLab"),
    ("gmail", "Gmail"),
    ("googleads", "Google Ads"),
    ("google_analytics", "Google Analytics"),
    ("googlebigquery", "Google BigQuery"),
    ("googlecalendar", "Google Calendar"),
    ("google_classroom", "Google Classroom"),
    ("googledocs", "Google Docs"),
    ("googledrive", "Google Drive"),
    ("google_maps", "Google Maps"),
    ("googlemeet", "Google Meet"),
    ("googlephotos", "Google Photos"),
    ("google_search_console", "Google Search Console"),
    ("googlesheets", "Google Sheets"),
    ("googleslides", "Google Slides"),
    ("googlesuper", "Google Super"),
    ("googletasks", "Google Tasks"),
    ("gorgias", "Gorgias"),
    ("gumroad", "Gumroad"),
    ("harvest", "Harvest"),
    ("hubspot", "HubSpot"),
    ("hugging_face", "Hugging Face"),
    ("instagram", "Instagram"),
    ("intercom", "Intercom"),
    ("jira", "Jira"),
    ("kit", "Kit"),
    ("linear", "Linear"),
    ("linkedin", "LinkedIn"),
    ("linkhut", "Linkhut"),
    ("mailchimp", "Mailchimp"),
    ("microsoft_teams", "Microsoft Teams"),
    ("miro", "Miro"),
    ("monday", "Monday"),
    ("moneybird", "Moneybird"),
    ("mural", "Mural"),
    ("notion", "Notion"),
    ("omnisend", "Omnisend"),
    ("one_drive", "OneDrive"),
    ("outlook", "Outlook"),
    ("pagerduty", "PagerDuty"),
    ("prisma", "Prisma"),
    ("productboard", "Productboard"),
    ("pushbullet", "Pushbullet"),
    ("quickbooks", "QuickBooks"),
    ("reddit", "Reddit"),
    ("reddit_ads", "Reddit Ads"),
    ("roam", "Roam"),
    ("salesforce", "Salesforce"),
    ("sentry", "Sentry"),
    ("servicem8", "Servicem8"),
    ("share_point", "SharePoint"),
    ("shippo", "Shippo"),
    ("slack", "Slack"),
    ("slackbot", "Slackbot"),
    ("splitwise", "Splitwise"),
    ("square", "Square"),
    ("stack_exchange", "Stack Exchange"),
    ("strava", "Strava"),
    ("stripe", "Stripe"),
    ("supabase", "Supabase"),
    ("ticketmaster", "Ticketmaster"),
    ("ticktick", "Ticktick"),
    ("timely", "Timely"),
    ("todoist", "Todoist"),
    ("toneden", "Toneden"),
    ("trello", "Trello"),
    ("typeform", "Typeform"),
    ("wakatime", "WakaTime"),
    ("webex", "Webex"),
    ("whatsapp", "WhatsApp Business"),
    ("wrike", "Wrike"),
    ("yandex", "Yandex"),
    ("ynab", "YNAB"),
    ("youtube", "YouTube"),
    ("zendesk", "Zendesk"),
    ("zoho", "Zoho"),
    ("zoho_bigin", "Zoho Bigin"),
    ("zoho_books", "Zoho Books"),
    ("zoho_desk", "Zoho Desk"),
    ("zoho_inventory", "Zoho Inventory"),
    ("zoho_invoice", "Zoho Invoice"),
    ("zoho_mail", "Zoho Mail"),
    ("zoom", "Zoom"),
)

_CATEGORY_ORDER = (
    "communication",
    "office",
    "mail_calendar",
    "docs_storage",
    "project_management",
    "development",
    "crm_sales",
    "commerce_payments",
    "social_media",
    "automation",
)

_CATEGORY_LABELS = {
    "communication": "Communication",
    "office": "Office",
    "mail_calendar": "Mail & Calendar",
    "docs_storage": "Docs & Storage",
    "project_management": "Project Management",
    "development": "Development",
    "crm_sales": "CRM & Sales",
    "commerce_payments": "Commerce & Payments",
    "social_media": "Social Media",
    "automation": "Automation",
}

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("communication", ("slack", "discord", "teams", "telegram", "whatsapp", "webex", "dialpad", "googlemeet", "zoom")),
    ("mail_calendar", ("gmail", "outlook", "calendar", "calendly", "cal", "mail", "googlecalendar")),
    ("docs_storage", ("drive", "docs", "sheets", "slides", "dropbox", "box", "share_point", "one_drive", "airtable", "notion", "confluence")),
    ("project_management", ("asana", "trello", "jira", "linear", "clickup", "basecamp", "monday", "wrike", "todoist", "ticktick", "productboard")),
    ("development", ("github", "gitlab", "bitbucket", "digital_ocean", "supabase", "convex", "prisma", "sentry", "wakatime", "contentful")),
    ("crm_sales", ("salesforce", "hubspot", "zoho", "zendesk", "intercom", "capsule", "attio", "gorgias", "servicem8")),
    ("commerce_payments", ("stripe", "shopify", "square", "quickbooks", "freshbooks", "freeagent", "moneybird", "ynab", "gumroad", "shippo")),
    ("social_media", ("facebook", "instagram", "linkedin", "reddit", "youtube", "twitter", "x", "spotify", "stack_exchange")),
    ("office", ("excel", "figma", "canva", "miro", "mural", "typeform", "google", "microsoft")),
)


def category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, "Automation")


def _category_for(slug: str, name: str) -> str:
    key = f"{slug} {name}".lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in key for keyword in keywords):
            return category
    return "automation"


def _description_for(name: str, category: str) -> str:
    label = category_label(category)
    if category == "communication":
        return f"Connect {name} for messages, channels, meetings, and team communication workflows."
    if category == "mail_calendar":
        return f"Connect {name} for email, calendar, scheduling, and inbox workflows."
    if category == "docs_storage":
        return f"Connect {name} for documents, files, knowledge bases, and workspace content."
    if category == "project_management":
        return f"Connect {name} for tasks, issues, projects, and delivery tracking."
    if category == "development":
        return f"Connect {name} for developer, repository, deployment, and observability workflows."
    if category == "crm_sales":
        return f"Connect {name} for CRM, customer support, sales, and account workflows."
    if category == "commerce_payments":
        return f"Connect {name} for commerce, billing, payments, and finance workflows."
    if category == "social_media":
        return f"Connect {name} for social publishing, community, and audience workflows."
    if category == "office":
        return f"Connect {name} for office productivity, design, whiteboard, and collaboration workflows."
    return f"Connect {name} through the Composio-compatible {label} software interface catalog."


def list_software_interfaces() -> list[SoftwareInterface]:
    interfaces: list[SoftwareInterface] = []
    for slug, name in COMPOSIO_TOOLKITS:
        category = _category_for(slug, name)
        interfaces.append(
            SoftwareInterface(
                slug=slug,
                name=name,
                category=category,
                description=_description_for(name, category),
            )
        )
    return interfaces


def get_software_interface(slug: str) -> SoftwareInterface | None:
    normalized = slug.strip().lower().replace("-", "_")
    for item in list_software_interfaces():
        if item.slug == normalized:
            return item
    return None


def summarize_categories() -> list[dict[str, object]]:
    counts = {category: 0 for category in _CATEGORY_ORDER}
    for item in list_software_interfaces():
        counts[item.category] = counts.get(item.category, 0) + 1
    return [{"id": category, "label": category_label(category), "count": counts.get(category, 0)} for category in _CATEGORY_ORDER if counts.get(category, 0) > 0]

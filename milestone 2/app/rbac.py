"""Role-Based Access Control (RBAC) for FreightQuote AI.
Defines page access and capabilities per role as required by Milestone 2 Step 5.
"""

# Pages that each role may see in navigation and open via /api/page/{pid}
ROLE_MENU = {
    "Admin": {
        "copilot", "route", "quotes", "carriers", "weather", "margin", "customs", "profile", "admin"
    },
    "Operations Manager": {
        "copilot", "route", "carriers", "weather", "customs", "profile"
    },
    "Freight Broker": {
        "copilot", "quotes", "carriers", "margin", "profile"
    },
    "Auditor": {
        "copilot", "route", "quotes", "carriers", "weather", "margin", "customs", "profile"
    },
    "Customer": {
        "copilot", "quotes", "profile"
    },
}

# Granular capabilities for action routes and page functions
ROLE_CAPS = {
    "Admin": {
        "view", "copilot", "route", "quotes", "carriers", "weather", "margin", "customs",
        "profile", "admin", "users", "run", "reroute", "storm", "quote", "quote_create", "customs_edit"
    },
    "Operations Manager": {
        "view", "copilot", "route", "carriers", "weather", "customs", "profile",
        "run", "reroute", "storm", "customs_edit"
    },
    "Freight Broker": {
        "view", "copilot", "quotes", "carriers", "margin", "profile",
        "quote", "quote_create"
    },
    "Auditor": {
        "view", "copilot", "route", "quotes", "carriers", "weather", "margin", "customs", "profile"
        # Strictly read-only: no run, reroute, storm, quote, customs_edit, or users
    },
    "Customer": {
        "view", "copilot", "quotes", "profile"
        # Scoped to own customer_id
    },
}

ALL_MENU_ITEMS = [
    ("copilot", "AI Copilot", "bot"),
    ("route", "Agent 1 · Route AI", "route"),
    ("quotes", "Agent 2 · Spot Quotes", "dollar"),
    ("carriers", "Agent 3 · Carriers", "truck"),
    ("weather", "Agent 4 · Weather Risk", "cloud"),
    ("margin", "Agent 5 · Margin", "trend"),
    ("customs", "Agent 6 · Customs", "file"),
    ("profile", "My Profile", "user"),
    ("admin", "Admin Dashboard", "shield"),
]

def menu_for_role(role):
    allowed_ids = ROLE_MENU.get(role, set())
    return [{"id": item[0], "label": item[1], "icon": item[2]} for item in ALL_MENU_ITEMS if item[0] in allowed_ids]

def check_permission(role, capability):
    if not role:
        return False
    return capability in ROLE_CAPS.get(role, set())

def can_access_page(role, page_id):
    if not role:
        return False
    return page_id in ROLE_MENU.get(role, set())

def can_access_entity(role, eid, customer_id=None):
    if not role:
        return False
    if role in ("Admin", "Auditor"):
        return True
    eid = str(eid)
    if eid.startswith("QTE"):
        if role == "Freight Broker":
            return True
        if role == "Customer":
            return bool(customer_id)
        return False
    if eid.startswith("SHP"):
        if role == "Operations Manager":
            return True
        if role == "Customer":
            return bool(customer_id)
        return False
    # Ports
    if role == "Operations Manager":
        return True
    return False

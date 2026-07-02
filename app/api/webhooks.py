"""REMOVED — this router was never mounted and had drifted from the live code.

The live webhook handlers are in app/main.py (/webhooks/meta, /webhooks/retell,
/webhooks/twilio/sms, /webhooks/twilio/status). This file previously duplicated
them against `request.state.*` dependencies that nothing ever set — any edit
made here silently did nothing. Kept as a stub so stale imports fail loudly.
"""

raise ImportError(
    "app.api.webhooks was removed — webhook handlers live in app/main.py"
)

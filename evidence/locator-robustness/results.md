# Locator robustness
- baseline: ok=True unique semantic match
- A-D wrap/order/css/branding: ok=True unique semantic match
- E duplicate Search: ok=False ambiguous: winner 100 vs second 100
- F semantic label change: ok=False winner score 60 below threshold 70
- F-override harbor label: ok=True unique semantic match

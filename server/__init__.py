"""FastAPI backend for the Franklin housing webapp.

Thin read-only HTTP layer over the franklin_housing library. The county API is
never hit in the request path — only by server/jobs/refresh.py on a schedule.
"""

"""
ETL Sub-App

Handles all ETL-related functionality:
- ETL page views (model_etl)
- ETL job management APIs (CRUD, run, pause, etc.)
- Cloud Scheduler webhook handlers
- ETL run monitoring and status

This sub-app was extracted from the monolithic views.py to improve
maintainability and code organization.
"""

# CFIPS Policy Simulation Dashboard

A Streamlit dashboard for testing CCAP fraud-prevention policy scenarios.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Required upload fields
- provider_id
- risk_score
- payment_amount_current

## Optional fields
- provider_name
- region
- provider_type
- network_risk_score

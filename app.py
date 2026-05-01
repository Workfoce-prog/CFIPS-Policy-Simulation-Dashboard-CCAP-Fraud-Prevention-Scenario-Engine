
import os
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CFIPS Policy Simulation", page_icon="📊", layout="wide")
st.title("📊 CFIPS Policy Simulation Dashboard")
st.caption("Test payment-hold thresholds, audit capacity, review rules, and expected savings.")

@st.cache_data
def load_data():
    return pd.read_csv("sample_policy_simulation_data.csv") if os.path.exists("sample_policy_simulation_data.csv") else pd.DataFrame()

def band(x, amber, red):
    if x >= red:
        return "Red"
    if x >= amber:
        return "Amber"
    return "Green"

def run_sim(df, amber, red, audit_capacity, amber_review_rate, fraud_red, fraud_amber, audit_cost, fp_cost, hold_red, review_amber):
    d = df.copy()
    d["risk_score"] = pd.to_numeric(d["risk_score"], errors="coerce").fillna(0)
    d["network_risk_score"] = pd.to_numeric(d.get("network_risk_score", 0), errors="coerce").fillna(0)
    d["payment_amount_current"] = pd.to_numeric(d["payment_amount_current"], errors="coerce").fillna(0)
    d["sim_band"] = d["risk_score"].apply(lambda v: band(v, amber, red))
    d["sim_decision"] = "AUTO APPROVE"
    if review_amber:
        d.loc[d["sim_band"].eq("Amber"), "sim_decision"] = "REVIEW REQUIRED"
    if hold_red:
        d.loc[d["sim_band"].eq("Red"), "sim_decision"] = "HOLD PAYMENT"
    amber_n = int((d["sim_band"].eq("Amber")).sum() * amber_review_rate)
    queue = pd.concat([
        d[d["sim_band"].eq("Red")],
        d[d["sim_band"].eq("Amber")].sort_values("risk_score", ascending=False).head(amber_n)
    ]).sort_values(["risk_score","network_risk_score"], ascending=False)
    audited_ids = set(queue.head(audit_capacity)["provider_id"])
    d["selected_for_audit"] = d["provider_id"].isin(audited_ids).astype(int)
    d["expected_fraud_probability"] = np.select(
        [d["sim_band"].eq("Red"), d["sim_band"].eq("Amber")],
        [fraud_red, fraud_amber],
        default=0.02
    )
    d["expected_improper_payment"] = d["payment_amount_current"] * d["expected_fraud_probability"]
    d["expected_prevented_payment"] = np.where(d["sim_decision"].eq("HOLD PAYMENT"), d["expected_improper_payment"], 0)
    d["expected_review_recovery"] = np.where((d["selected_for_audit"].eq(1)) & (~d["sim_decision"].eq("HOLD PAYMENT")), d["expected_improper_payment"] * 0.45, 0)
    d["expected_total_savings"] = d["expected_prevented_payment"] + d["expected_review_recovery"]
    d["false_positive_flag"] = np.where(d["sim_decision"].isin(["HOLD PAYMENT","REVIEW REQUIRED"]) & (d["expected_fraud_probability"] < .20), 1, 0)
    audit_total = len(audited_ids) * audit_cost
    fp_total = d["false_positive_flag"].sum() * fp_cost
    gross = d["expected_total_savings"].sum()
    summary = {
        "red": int((d["sim_band"]=="Red").sum()),
        "amber": int((d["sim_band"]=="Amber").sum()),
        "green": int((d["sim_band"]=="Green").sum()),
        "held": float(d.loc[d["sim_decision"].eq("HOLD PAYMENT"), "payment_amount_current"].sum()),
        "gross": float(gross),
        "costs": float(audit_total + fp_total),
        "net": float(gross - audit_total - fp_total),
        "audited": len(audited_ids),
        "false_positive": int(d["false_positive_flag"].sum())
    }
    return d, summary, queue.head(audit_capacity)

uploaded = st.sidebar.file_uploader("Upload scored provider CSV", type=["csv"])
raw = pd.read_csv(uploaded) if uploaded else load_data()

for c,v in {"provider_name":"","region":"Unknown","provider_type":"Unknown","network_risk_score":0}.items():
    if c not in raw.columns:
        raw[c] = v

missing = [c for c in ["provider_id","risk_score","payment_amount_current"] if c not in raw.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

st.sidebar.header("Policy Levers")
amber = st.sidebar.slider("Amber threshold", .20, .90, .60, .01)
red = st.sidebar.slider("Red threshold", .40, 1.20, .85, .01)
audit_capacity = st.sidebar.slider("Monthly audit capacity", 5, 200, 50, 5)
amber_review_rate = st.sidebar.slider("Amber review rate", 0.0, 1.0, .35, .05)
hold_red = st.sidebar.checkbox("Hold Red payments", True)
review_amber = st.sidebar.checkbox("Review Amber providers", True)

st.sidebar.header("Assumptions")
fraud_red = st.sidebar.slider("Assumed fraud probability: Red", .05, .90, .45, .01)
fraud_amber = st.sidebar.slider("Assumed fraud probability: Amber", .01, .60, .18, .01)
audit_cost = st.sidebar.number_input("Cost per audit/review", min_value=0, value=1200, step=100)
fp_cost = st.sidebar.number_input("False-positive burden cost", min_value=0, value=500, step=100)

res, summary, audited = run_sim(raw, amber, red, audit_capacity, amber_review_rate, fraud_red, fraud_amber, audit_cost, fp_cost, hold_red, review_amber)

tabs = st.tabs(["Scenario Summary","Tradeoffs","Audit Queue","Provider Results","Compare Scenarios","Methodology"])

with tabs[0]:
    st.header("Scenario Summary")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Red Providers", summary["red"])
    c2.metric("Amber Providers", summary["amber"])
    c3.metric("Payment Held", f"${summary['held']:,.0f}")
    c4.metric("Gross Savings", f"${summary['gross']:,.0f}")
    c5.metric("Net Savings", f"${summary['net']:,.0f}")
    c6,c7,c8 = st.columns(3)
    c6.metric("Audited", summary["audited"])
    c7.metric("False Positives", summary["false_positive"])
    c8.metric("Audit + Burden Costs", f"${summary['costs']:,.0f}")
    st.subheader("Risk Band Distribution")
    st.bar_chart(res["sim_band"].value_counts().reindex(["Red","Amber","Green"]).fillna(0))
    st.subheader("Decision Distribution")
    st.bar_chart(res["sim_decision"].value_counts())

with tabs[1]:
    st.header("Policy Tradeoffs")
    trade = pd.DataFrame([
        ["Payment Held", summary["held"]],
        ["Gross Expected Savings", summary["gross"]],
        ["Audit + Burden Costs", summary["costs"]],
        ["Net Expected Savings", summary["net"]],
    ], columns=["Metric","Value"])
    st.dataframe(trade, use_container_width=True)
    st.bar_chart(trade.set_index("Metric"))
    st.subheader("Regional Impact")
    region = res.groupby("region", as_index=False).agg(
        providers=("provider_id","count"),
        red=("sim_band", lambda x: int((x=="Red").sum())),
        expected_savings=("expected_total_savings","sum"),
        false_positive_count=("false_positive_flag","sum")
    )
    st.dataframe(region, use_container_width=True)

with tabs[2]:
    st.header("Audit Queue")
    cols = ["provider_id","provider_name","region","provider_type","risk_score","network_risk_score","sim_band","sim_decision","payment_amount_current","expected_fraud_probability","expected_total_savings"]
    available_cols = [c for c in cols if c in audited.columns]

if audited.empty:
    st.info("No providers selected for audit under the current policy scenario.")
else:
    st.dataframe(audited[available_cols], use_container_width=True, height=460)

with tabs[3]:
    st.header("Provider-Level Simulation Results")

    cols = ["provider_id","provider_name","region","provider_type",
            "risk_score","network_risk_score","sim_band","sim_decision",
            "selected_for_audit","payment_amount_current",
            "expected_fraud_probability","expected_improper_payment",
            "expected_total_savings","false_positive_flag"]

    available_cols = [c for c in cols if c in res.columns]

    if res.empty:
        st.info("No provider results available.")
    else:
        st.dataframe(
            res.sort_values(["risk_score","network_risk_score"], ascending=False)[available_cols],
            use_container_width=True,
            height=520
        )
    st.download_button("Download simulation results CSV", res.to_csv(index=False).encode("utf-8"), "cfips_policy_simulation_results.csv", "text/csv")

with tabs[4]:
    st.header("Compare Scenarios")
    scenarios = [
        ("Conservative", .70, .95, int(audit_capacity*.8), .20),
        ("Balanced", .60, .85, audit_capacity, .35),
        ("Aggressive", .50, .75, int(audit_capacity*1.25), .60),
    ]
    rows = []
    for name,a,r,cap,arr in scenarios:
        _, s, _ = run_sim(raw, a, r, cap, arr, fraud_red, fraud_amber, audit_cost, fp_cost, hold_red, review_amber)
        rows.append({"scenario":name,"amber_threshold":a,"red_threshold":r,"audit_capacity":cap,"amber_review_rate":arr,"red_count":s["red"],"payment_held":s["held"],"gross_savings":s["gross"],"net_savings":s["net"],"false_positive":s["false_positive"]})
    comp = pd.DataFrame(rows)
    st.dataframe(comp, use_container_width=True)
    st.bar_chart(comp.set_index("scenario")[["gross_savings","net_savings"]])

with tabs[5]:
    st.header("Methodology")
    st.markdown("""
### Purpose
This dashboard tests policy choices before deployment.

### Core formulas
Expected Improper Payment = Payment Amount × Assumed Fraud Probability

Net Expected Savings = Expected Prevented Payment + Review Recovery − Audit Costs − False-Positive Burden Costs

### Policy levers
- Amber and Red thresholds
- Audit capacity
- Amber review rate
- Whether Red payments are held
- Assumed fraud probabilities
- Cost assumptions

### Interpretation
A strong policy scenario balances fraud prevention with manageable audit workload and provider burden.
""")

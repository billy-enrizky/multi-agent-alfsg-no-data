import streamlit as st
import pandas as pd
import logging
import io
import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from multi_agent_system import create_multi_agent_graph, process_patient_day

load_dotenv()

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Multi-Agent ALFSG Predictor",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .agent-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border-left: 5px solid #1f77b4;
    }
    .decision-yes {
        color: #28a745;
        font-weight: bold;
        font-size: 1.2rem;
    }
    .decision-no {
        color: #dc3545;
        font-weight: bold;
        font-size: 1.2rem;
    }
    .final-prediction {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin: 2rem 0;
    }
    </style>
""", unsafe_allow_html=True)


def check_auth():
    """Check authentication using session state."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = ""

    if st.session_state.authenticated:
        return True

    st.title("Multi-Agent ALFSG Predictor")
    st.markdown("---")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        expected_password = os.getenv("STREAMLIT_PASSWORD", "")
        if not expected_password:
            st.error("STREAMLIT_PASSWORD not configured in .env")
            return False
        if password == expected_password and username.strip():
            st.session_state.authenticated = True
            st.session_state.username = username.strip()
            st.rerun()
        else:
            st.error("Invalid credentials")

    return False


@st.cache_data
def load_vignettes():
    """Load clinical vignettes from Azure Blob Storage."""
    try:
        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
        container_name = os.getenv("AZURE_STORAGE_CONTAINER", "clinical-data")

        if not account_name or not account_key:
            st.error("Azure Storage credentials not configured in .env")
            return None

        blob_service = BlobServiceClient(
            account_url=f"https://{account_name}.blob.core.windows.net",
            credential=account_key,
        )
        blob_client = blob_service.get_blob_client(
            container=container_name, blob="clinical_vignettes.xlsx"
        )
        download_stream = blob_client.download_blob()
        data = download_stream.readall()
        df = pd.read_excel(io.BytesIO(data))
        return df
    except Exception as e:
        logger.error(f"Error loading clinical vignettes from blob storage: {e}")
        st.error(f"Error loading clinical vignettes from Azure Blob Storage: {e}")
        return None


@st.cache_resource
def get_graph():
    """Get the compiled LangGraph workflow."""
    return create_multi_agent_graph()


def format_confidence(confidence):
    """Format confidence as percentage."""
    return f"{confidence * 100:.1f}%"


def display_agent_decision(title, agent_output):
    """Display a single agent's decision."""
    st.subheader(title)
    if agent_output:
        decision_color = "#28a745" if agent_output.decision == "Yes" else "#dc3545"
        st.markdown(
            f'<p style="color: {decision_color}; font-weight: bold; font-size: 1.2rem;">'
            f"Decision: {agent_output.decision}</p>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Confidence:** {format_confidence(agent_output.confidence)}")
        st.markdown("**Reasoning:**")
        st.write(agent_output.reasoning)
    else:
        st.error("No decision available")


def main():
    if not check_auth():
        return

    # Header with logout
    col_title, col_user = st.columns([4, 1])
    with col_title:
        st.title("Multi-Agent ALFSG Predictor")
    with col_user:
        st.markdown(f"**{st.session_state.username}**")
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.username = ""
            st.rerun()

    st.markdown("---")

    # Load data
    df = load_vignettes()
    if df is None:
        st.stop()

    # Sidebar
    with st.sidebar:
        st.header("Patient Selection")

        patient_ids = sorted(df["subject_id"].dropna().unique())
        if len(patient_ids) == 0:
            st.error("No patient IDs found in data")
            st.stop()

        selected_patient = st.selectbox(
            "Select Patient ID",
            options=patient_ids,
            format_func=lambda x: f"Patient {int(x)}",
        )

        patient_data = df[df["subject_id"] == selected_patient]
        available_days = sorted(patient_data["day"].dropna().unique())

        if len(available_days) == 0:
            st.warning(f"No days available for Patient {int(selected_patient)}")
            st.stop()

        selected_day = st.selectbox(
            "Select Day",
            options=available_days,
            format_func=lambda x: f"Day {int(x)}",
        )

        st.markdown("---")

        deployment = st.selectbox(
            "Model Deployment",
            options=["gpt-5.2", "gpt-5", "gpt-4.1-mini", "gpt-5-mini", "claude-opus-4-1", "claude-sonnet-4-5"],
            index=0,
        )

        st.markdown("---")

        predict_button = st.button(
            "Predict Survival",
            type="primary",
            use_container_width=True,
        )

    # Main content
    if predict_button:
        # Set deployment before running
        os.environ["DEPLOYMENT_NAME"] = deployment

        with st.spinner("Running multi-agent analysis..."):
            try:
                patient_row = df[
                    (df["subject_id"] == selected_patient) & (df["day"] == selected_day)
                ].iloc[0]

                graph = get_graph()
                outputs = process_patient_day(patient_row, graph)

                st.success("Prediction completed")
                st.markdown("---")

                # Clinical vignettes
                st.header("Clinical Vignettes")
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.subheader("Hepatologist")
                    vignette = patient_row.get("hepatologist_vignette", "N/A")
                    st.text_area("", value=vignette, height=300, disabled=True, key="hep_vig")

                with col2:
                    st.subheader("Critical Care Physician")
                    vignette = patient_row.get("critical_care_physician_vignette", "N/A")
                    st.text_area("", value=vignette, height=300, disabled=True, key="cc_vig")

                with col3:
                    st.subheader("Transplant Surgeon")
                    vignette = patient_row.get("transplant_surgeon_vignette", "N/A")
                    st.text_area("", value=vignette, height=300, disabled=True, key="ts_vig")

                st.markdown("---")

                # Agent decisions
                st.header("Agent Decisions")
                hepatologist = outputs.get("hepatologist_output")
                critical_care = outputs.get("critical_care_output")
                transplant_surgeon = outputs.get("transplant_surgeon_output")

                col1, col2, col3 = st.columns(3)
                with col1:
                    display_agent_decision("Hepatologist", hepatologist)
                with col2:
                    display_agent_decision("Critical Care Physician", critical_care)
                with col3:
                    display_agent_decision("Transplant Surgeon", transplant_surgeon)

                st.markdown("---")

                # Final prediction
                final_pred = outputs.get("final_prediction")
                if final_pred:
                    st.markdown('<div class="final-prediction">', unsafe_allow_html=True)
                    st.markdown("## Final Committee Prediction")

                    decision_color = "#28a745" if final_pred.prediction == "Yes" else "#dc3545"
                    st.markdown(
                        f'<p style="font-size: 2rem; margin: 1rem 0;">'
                        f'<span style="color: {decision_color}; font-weight: bold;">'
                        f"Prediction: {final_pred.prediction}</span></p>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<p style="font-size: 1.5rem; margin: 1rem 0;">'
                        f"Confidence: {format_confidence(final_pred.confidence)}</p>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("### Committee Reasoning")
                    st.write(final_pred.reasoning)

                    # Voting breakdown with correct equal weights
                    st.markdown("### Voting Breakdown (Equal Weight: 33.33% each)")
                    if hepatologist and critical_care and transplant_surgeon:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Hepatologist (33.33%)", hepatologist.decision)
                        with col2:
                            st.metric("Critical Care (33.33%)", critical_care.decision)
                        with col3:
                            st.metric("Transplant Surgeon (33.33%)", transplant_surgeon.decision)
                else:
                    st.error("Final prediction not available")

                st.markdown("---")

                # Actual outcome
                if pd.notna(patient_row.get("Spont_Survival21")):
                    actual_survival = "Yes" if patient_row["Spont_Survival21"] == 1.0 else "No"
                    actual_color = "#28a745" if actual_survival == "Yes" else "#dc3545"
                    st.markdown(
                        f'<p style="font-size: 1.2rem; text-align: center; padding: 1rem; '
                        f'background-color: #f0f2f6; border-radius: 10px;">'
                        f'<strong>Actual 21-Day Survival:</strong> '
                        f'<span style="color: {actual_color}; font-weight: bold;">'
                        f"{actual_survival}</span></p>",
                        unsafe_allow_html=True,
                    )

                # Download results
                st.markdown("---")
                st.subheader("Download Results")

                result_data = {
                    "subject_id": [int(selected_patient)],
                    "day": [int(selected_day)],
                    "deployment": [deployment],
                    "final_prediction": [final_pred.prediction if final_pred else None],
                    "final_confidence": [final_pred.confidence if final_pred else None],
                    "final_reasoning": [final_pred.reasoning if final_pred else None],
                    "hepatologist_decision": [hepatologist.decision if hepatologist else None],
                    "hepatologist_confidence": [hepatologist.confidence if hepatologist else None],
                    "hepatologist_reasoning": [hepatologist.reasoning if hepatologist else None],
                    "critical_care_decision": [critical_care.decision if critical_care else None],
                    "critical_care_confidence": [critical_care.confidence if critical_care else None],
                    "critical_care_reasoning": [critical_care.reasoning if critical_care else None],
                    "transplant_surgeon_decision": [transplant_surgeon.decision if transplant_surgeon else None],
                    "transplant_surgeon_confidence": [transplant_surgeon.confidence if transplant_surgeon else None],
                    "transplant_surgeon_reasoning": [transplant_surgeon.reasoning if transplant_surgeon else None],
                    "actual_survival": [patient_row.get("Spont_Survival21", None)],
                }

                result_df = pd.DataFrame(result_data)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    result_df.to_excel(writer, sheet_name="Predictions", index=False)
                output.seek(0)

                st.download_button(
                    label="Download Prediction Results (Excel)",
                    data=output.getvalue(),
                    file_name=f"prediction_Patient_{int(selected_patient)}_Day_{int(selected_day)}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            except Exception as e:
                logger.error(f"Error processing prediction: {e}")
                st.error(f"Error processing prediction: {e}")
                st.exception(e)
    else:
        st.info("Select a patient and day from the sidebar, then click Predict Survival.")

        st.markdown("### Dataset Information")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Patients", len(patient_ids))
        with col2:
            st.metric("Total Records", len(df))
        with col3:
            st.metric("Days per Patient", f"{len(df) / len(patient_ids):.1f}")


if __name__ == "__main__":
    main()

import streamlit as st
import pandas as pd
import logging
import io
from multi_agent_system import create_multi_agent_graph, process_patient_day

# Configure page
st.set_page_config(
    page_title="Multi-Agent ALFSG Predictor",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
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
    .confidence-high {
        color: #28a745;
    }
    .confidence-medium {
        color: #ffc107;
    }
    .confidence-low {
        color: #dc3545;
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

@st.cache_data
def load_vignettes():
    """Load clinical vignettes data."""
    try:
        df = pd.read_excel('clinical_vignettes.xlsx')
        return df
    except Exception as e:
        st.error(f"Error loading clinical_vignettes.xlsx: {e}")
        return None

@st.cache_resource
def get_graph():
    """Get the compiled LangGraph workflow."""
    return create_multi_agent_graph()

def get_confidence_class(confidence):
    """Get CSS class for confidence score."""
    if confidence >= 0.7:
        return "confidence-high"
    elif confidence >= 0.4:
        return "confidence-medium"
    else:
        return "confidence-low"

def format_confidence(confidence):
    """Format confidence as percentage."""
    return f"{confidence * 100:.1f}%"

def main():
    # Header
    st.markdown('<h1 class="main-header">🏥 Multi-Agent ALFSG Predictor</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Load data
    df = load_vignettes()
    if df is None:
        st.stop()
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("📋 Patient Selection")
        
        # Get unique patient IDs
        patient_ids = sorted(df['subject_id'].dropna().unique())
        if len(patient_ids) == 0:
            st.error("No patient IDs found in data")
            st.stop()
        
        # Patient ID dropdown
        selected_patient = st.selectbox(
            "Select Patient ID",
            options=patient_ids,
            format_func=lambda x: f"Patient {int(x)}"
        )
        
        # Day dropdown (filtered by selected patient)
        patient_data = df[df['subject_id'] == selected_patient]
        available_days = sorted(patient_data['day'].dropna().unique())
        
        if len(available_days) == 0:
            st.warning(f"No days available for Patient {int(selected_patient)}")
            st.stop()
        
        selected_day = st.selectbox(
            "Select Day",
            options=available_days,
            format_func=lambda x: f"Day {int(x)}"
        )
        
        st.markdown("---")
        
        # Predict button
        predict_button = st.button(
            "🔮 Predict Survival",
            type="primary",
            use_container_width=True
        )
    
    # Main content area
    if predict_button:
        with st.spinner("🤖 Running multi-agent analysis... This may take a minute."):
            try:
                # Get patient data
                patient_row = df[(df['subject_id'] == selected_patient) & 
                                (df['day'] == selected_day)].iloc[0]
                
                # Get graph
                graph = get_graph()
                
                # Process prediction
                outputs = process_patient_day(patient_row, graph)
                
                # Display results
                st.success("✅ Prediction completed!")
                st.markdown("---")
                
                # Display vignettes for each agent
                st.header("📄 Clinical Vignettes")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.subheader("👨‍⚕️ Hepatologist")
                    vignette = patient_row.get('hepatologist_vignette', 'N/A')
                    st.markdown(f'<div style="white-space: pre-wrap; font-family: monospace; font-size: 0.9rem;">{vignette}</div>', unsafe_allow_html=True)
                
                with col2:
                    st.subheader("🏥 Critical Care Physician")
                    vignette = patient_row.get('critical_care_physician_vignette', 'N/A')
                    st.markdown(f'<div style="white-space: pre-wrap; font-family: monospace; font-size: 0.9rem;">{vignette}</div>', unsafe_allow_html=True)
                
                with col3:
                    st.subheader("🔪 Transplant Surgeon")
                    vignette = patient_row.get('transplant_surgeon_vignette', 'N/A')
                    st.markdown(f'<div style="white-space: pre-wrap; font-family: monospace; font-size: 0.9rem;">{vignette}</div>', unsafe_allow_html=True)
                
                st.markdown("---")
                
                # Display agent decisions
                st.header("🤖 Agent Decisions")
                
                col1, col2, col3 = st.columns(3)
                
                hepatologist = outputs.get('hepatologist_output')
                critical_care = outputs.get('critical_care_output')
                transplant_surgeon = outputs.get('transplant_surgeon_output')
                
                with col1:
                    st.subheader("👨‍⚕️ Hepatologist Decision")
                    if hepatologist:
                        decision_class = "decision-yes" if hepatologist.decision == "Yes" else "decision-no"
                        confidence_class = get_confidence_class(hepatologist.confidence)
                        st.markdown(f'<p class="{decision_class}">Decision: {hepatologist.decision}</p>', unsafe_allow_html=True)
                        st.markdown(f'<p class="{confidence_class}">Confidence: {format_confidence(hepatologist.confidence)}</p>', unsafe_allow_html=True)
                        st.markdown("**Reasoning:**")
                        st.write(hepatologist.reasoning)
                    else:
                        st.error("No decision available")
                
                with col2:
                    st.subheader("🏥 Critical Care Decision")
                    if critical_care:
                        decision_class = "decision-yes" if critical_care.decision == "Yes" else "decision-no"
                        confidence_class = get_confidence_class(critical_care.confidence)
                        st.markdown(f'<p class="{decision_class}">Decision: {critical_care.decision}</p>', unsafe_allow_html=True)
                        st.markdown(f'<p class="{confidence_class}">Confidence: {format_confidence(critical_care.confidence)}</p>', unsafe_allow_html=True)
                        st.markdown("**Reasoning:**")
                        st.write(critical_care.reasoning)
                    else:
                        st.error("No decision available")
                
                with col3:
                    st.subheader("🔪 Transplant Surgeon Decision")
                    if transplant_surgeon:
                        decision_class = "decision-yes" if transplant_surgeon.decision == "Yes" else "decision-no"
                        confidence_class = get_confidence_class(transplant_surgeon.confidence)
                        st.markdown(f'<p class="{decision_class}">Decision: {transplant_surgeon.decision}</p>', unsafe_allow_html=True)
                        st.markdown(f'<p class="{confidence_class}">Confidence: {format_confidence(transplant_surgeon.confidence)}</p>', unsafe_allow_html=True)
                        st.markdown("**Reasoning:**")
                        st.write(transplant_surgeon.reasoning)
                    else:
                        st.error("No decision available")
                
                st.markdown("---")
                
                # Display final prediction
                final_pred = outputs.get('final_prediction')
                if final_pred:
                    st.markdown('<div class="final-prediction">', unsafe_allow_html=True)
                    st.markdown("## 🎯 Final Committee Prediction")
                    
                    decision_class = "decision-yes" if final_pred.prediction == "Yes" else "decision-no"
                    confidence_class = get_confidence_class(final_pred.confidence)
                    
                    st.markdown(f'<p style="font-size: 2rem; margin: 1rem 0;"><span class="{decision_class}">Prediction: {final_pred.prediction}</span></p>', unsafe_allow_html=True)
                    st.markdown(f'<p style="font-size: 1.5rem; margin: 1rem 0;"><span class="{confidence_class}">Confidence: {format_confidence(final_pred.confidence)}</span></p>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    st.markdown("### 📝 Final Reasoning")
                    st.write(final_pred.reasoning)
                    
                    # Show weighted voting breakdown
                    st.markdown("### ⚖️ Weighted Voting Breakdown")
                    if hepatologist and critical_care and transplant_surgeon:
                        weights = {
                            'Critical Care': 0.40,
                            'Transplant Surgeon': 0.30,
                            'Hepatologist': 0.30
                        }
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Critical Care (40%)", critical_care.decision, delta=None)
                        with col2:
                            st.metric("Transplant Surgeon (30%)", transplant_surgeon.decision, delta=None)
                        with col3:
                            st.metric("Hepatologist (30%)", hepatologist.decision, delta=None)
                else:
                    st.error("Final prediction not available")
                
                st.markdown("---")
                
                # Show actual survival outcome at the bottom
                patient_row = df[(df['subject_id'] == selected_patient) & 
                                (df['day'] == selected_day)].iloc[0]
                if pd.notna(patient_row.get('Spont_Survival21')):
                    actual_survival = "Yes" if patient_row['Spont_Survival21'] == 1.0 else "No"
                    actual_class = "decision-yes" if actual_survival == "Yes" else "decision-no"
                    st.markdown(f'<p style="font-size: 1.2rem; text-align: center; padding: 1rem; background-color: #f0f2f6; border-radius: 10px;"><strong>Actual 21-Day Survival:</strong> <span class="{actual_class}">{actual_survival}</span></p>', unsafe_allow_html=True)
                
                # Download button
                st.markdown("---")
                st.subheader("📥 Download Results")
                
                # Create DataFrame with prediction results
                result_data = {
                    'subject_id': [int(selected_patient)],
                    'day': [int(selected_day)],
                    'final_prediction': [final_pred.prediction if final_pred else None],
                    'final_confidence': [final_pred.confidence if final_pred else None],
                    'final_reasoning': [final_pred.reasoning if final_pred else None],
                    'hepatologist_decision': [hepatologist.decision if hepatologist else None],
                    'hepatologist_confidence': [hepatologist.confidence if hepatologist else None],
                    'hepatologist_reasoning': [hepatologist.reasoning if hepatologist else None],
                    'critical_care_decision': [critical_care.decision if critical_care else None],
                    'critical_care_confidence': [critical_care.confidence if critical_care else None],
                    'critical_care_reasoning': [critical_care.reasoning if critical_care else None],
                    'transplant_surgeon_decision': [transplant_surgeon.decision if transplant_surgeon else None],
                    'transplant_surgeon_confidence': [transplant_surgeon.confidence if transplant_surgeon else None],
                    'transplant_surgeon_reasoning': [transplant_surgeon.reasoning if transplant_surgeon else None],
                    'actual_survival': [patient_row.get('Spont_Survival21', None)]
                }
                
                result_df = pd.DataFrame(result_data)
                
                # Create Excel file in memory
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    result_df.to_excel(writer, sheet_name='Predictions', index=False)
                output.seek(0)
                
                # Download button
                st.download_button(
                    label="📥 Download Prediction Results (Excel)",
                    data=output.getvalue(),
                    file_name=f"prediction_Patient_{int(selected_patient)}_Day_{int(selected_day)}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"Error processing prediction: {e}")
                st.exception(e)
    else:
        # Show instructions when button not clicked
        st.info("👈 Select a patient and day from the sidebar, then click **Predict Survival** to see the multi-agent analysis.")
        
        # Show sample data info
        st.markdown("### 📊 Dataset Information")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Patients", len(patient_ids))
        with col2:
            st.metric("Total Records", len(df))
        with col3:
            st.metric("Days per Patient", f"{len(df) / len(patient_ids):.1f}")

if __name__ == "__main__":
    main()


import os
import json
import logging
import pandas as pd
from typing import Literal, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Pydantic models for structured outputs
class AgentDecision(BaseModel):
    """Individual agent decision output."""
    decision: Literal["Yes", "No"] = Field(description="Prediction: Will patient survive 21 days? Yes or No")
    reasoning: str = Field(description="Detailed clinical reasoning for the decision")

class FinalPrediction(BaseModel):
    """Final committee prediction output."""
    prediction: Literal["Yes", "No"] = Field(description="Final prediction: Will patient survive 21 days? Yes or No")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Synthesis of all agent inputs with weighted analysis")
    hepatologist_decision: str = Field(description="Hepatologist decision and reasoning")
    critical_care_decision: str = Field(description="Critical Care Physician decision and reasoning")
    transplant_surgeon_decision: str = Field(description="Transplant Surgeon decision and reasoning")

# State definition for LangGraph
class AgentState(TypedDict):
    """State passed between nodes in the graph."""
    subject_id: int
    day: int
    hepatologist_vignette: str
    critical_care_physician_vignette: str
    transplant_surgeon_vignette: str
    hepatologist_output: AgentDecision | None
    critical_care_output: AgentDecision | None
    transplant_surgeon_output: AgentDecision | None
    final_prediction: FinalPrediction | None

def get_azure_openai_client():
    """Initialize Azure OpenAI client with API key authentication."""
    endpoint = os.getenv("ENDPOINT_URL", "https://acf-project.openai.azure.com/openai/v1")
    deployment_name = os.getenv("DEPLOYMENT_NAME", "gpt-4o")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(
        base_url=endpoint,
        api_key=api_key
    )
    
    return client, deployment_name


def hepatologist_agent(state: AgentState) -> AgentState:
    """AI Hepatologist agent node."""
    logger.info(f"Processing Hepatologist agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['hepatologist_vignette']
    
    system_prompt = """You are an AI Hepatologist specializing in acute liver failure and liver transplantation.
Your role is to analyze clinical data related to liver function, hepatic encephalopathy, and liver-related complications.
Based on the clinical vignette provided, predict whether the patient will achieve spontaneous survival at 21 days (without liver transplantation).

Consider:
- Liver synthetic function (INR, Prothrombin time, Bilirubin, ALT)
- Hepatic encephalopathy grade
- Ammonia levels
- Platelet count and coagulation status
- Patient demographics and prior treatments
- Trends in liver function markers

Provide a clear decision (Yes or No) and detailed clinical reasoning."""

    prompt = f"""{system_prompt}

Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    try:
        client, deployment_name = get_azure_openai_client()
        
        # Use JSON mode for structured output
        json_schema = AgentDecision.model_json_schema()
        json_prompt = f"""{prompt}

Please respond with a JSON object matching this schema:
{json_schema}

Return only valid JSON, no additional text."""
        
        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=16384,
        )
        
        response_text = completion.choices[0].message.content
        response_json = json.loads(response_text)
        decision = AgentDecision(**response_json)
        
        state['hepatologist_output'] = decision
        logger.info(f"Hepatologist decision: {decision.decision}")
        
    except Exception as e:
        logger.error(f"Error in Hepatologist agent: {e}")
        # Fallback to basic completion
        try:
            client, deployment_name = get_azure_openai_client()
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=16384,
            )
            response_text = completion.choices[0].message.content
            # Parse response manually
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            state['hepatologist_output'] = AgentDecision(
                decision=decision_val,
                reasoning=response_text
            )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            state['hepatologist_output'] = AgentDecision(
                decision="No",
                reasoning=f"Error processing: {str(e2)}"
            )
    
    return state

def critical_care_agent(state: AgentState) -> AgentState:
    """AI Critical Care Physician agent node."""
    logger.info(f"Processing Critical Care Physician agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['critical_care_physician_vignette']
    
    system_prompt = """You are an AI Critical Care Physician specializing in intensive care management of acute liver failure patients.
Your role is to analyze ICU-related parameters, organ support, and critical care interventions.
Based on the clinical vignette provided, predict whether the patient will achieve spontaneous survival at 21 days (without liver transplantation).

Consider:
- Respiratory status (ventilation, PaO2/FiO2 ratio)
- Hemodynamic status (vasopressor support)
- Renal function (creatinine, CVVH)
- Metabolic status (lactate, pH, bicarbonate, phosphate)
- Infection status
- White blood cell counts and inflammatory markers
- Trends in critical care parameters

Provide a clear decision (Yes or No) and detailed clinical reasoning."""

    prompt = f"""{system_prompt}

Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    try:
        client, deployment_name = get_azure_openai_client()
        
        # Use JSON mode for structured output
        json_schema = AgentDecision.model_json_schema()
        json_prompt = f"""{prompt}

Please respond with a JSON object matching this schema:
{json_schema}

Return only valid JSON, no additional text."""
        
        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=16384,
        )
        
        response_text = completion.choices[0].message.content
        response_json = json.loads(response_text)
        decision = AgentDecision(**response_json)
        
        state['critical_care_output'] = decision
        logger.info(f"Critical Care decision: {decision.decision}")
        
    except Exception as e:
        logger.error(f"Error in Critical Care agent: {e}")
        try:
            client, deployment_name = get_azure_openai_client()
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=16384,
            )
            response_text = completion.choices[0].message.content
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            state['critical_care_output'] = AgentDecision(
                decision=decision_val,
                reasoning=response_text
            )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            state['critical_care_output'] = AgentDecision(
                decision="No",
                reasoning=f"Error processing: {str(e2)}"
            )
    
    return state

def transplant_surgeon_agent(state: AgentState) -> AgentState:
    """AI Transplant Surgeon agent node."""
    logger.info(f"Processing Transplant Surgeon agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['transplant_surgeon_vignette']
    
    system_prompt = """You are an AI Transplant Surgeon specializing in liver transplantation for acute liver failure.
Your role is to analyze surgical and MELD-related parameters to assess transplant candidacy and survival probability.
Based on the clinical vignette provided, predict whether the patient will achieve spontaneous survival at 21 days (without liver transplantation).

Consider:
- MELD-related parameters (Bilirubin, Creatinine, INR, Sodium)
- Hemoglobin and blood product needs
- Platelet count and bleeding risk
- Respiratory failure (PaO2/FiO2 ratio)
- Organ support requirements (ventilation, vasopressors, CVVH)
- Infection status
- Overall surgical risk and transplant urgency

Provide a clear decision (Yes or No) and detailed clinical reasoning."""

    prompt = f"""{system_prompt}

Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    try:
        client, deployment_name = get_azure_openai_client()
        
        # Use JSON mode for structured output
        json_schema = AgentDecision.model_json_schema()
        json_prompt = f"""{prompt}

Please respond with a JSON object matching this schema:
{json_schema}

Return only valid JSON, no additional text."""
        
        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=16384,
        )
        
        response_text = completion.choices[0].message.content
        response_json = json.loads(response_text)
        decision = AgentDecision(**response_json)
        
        state['transplant_surgeon_output'] = decision
        logger.info(f"Transplant Surgeon decision: {decision.decision}")
        
    except Exception as e:
        logger.error(f"Error in Transplant Surgeon agent: {e}")
        try:
            client, deployment_name = get_azure_openai_client()
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=16384,
            )
            response_text = completion.choices[0].message.content
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            state['transplant_surgeon_output'] = AgentDecision(
                decision=decision_val,
                reasoning=response_text
            )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            state['transplant_surgeon_output'] = AgentDecision(
                decision="No",
                reasoning=f"Error processing: {str(e2)}"
            )
    
    return state

def final_synthesis(state: AgentState) -> AgentState:
    """AI Transplant Leader Committee - final synthesis with weighted analysis."""
    logger.info(f"Processing Final Synthesis for subject {state['subject_id']}, day {state['day']}")
    
    hepatologist = state['hepatologist_output']
    critical_care = state['critical_care_output']
    transplant_surgeon = state['transplant_surgeon_output']
    
    # Weighting: Critical Care=40%, Surgeon=30%, Hepatologist=30%
    weights = {
        'critical_care': 0.40,
        'transplant_surgeon': 0.30,
        'hepatologist': 0.30
    }
    
    # Calculate weighted score
    yes_votes = 0.0
    if critical_care and critical_care.decision == "Yes":
        yes_votes += weights['critical_care']
    if transplant_surgeon and transplant_surgeon.decision == "Yes":
        yes_votes += weights['transplant_surgeon']
    if hepatologist and hepatologist.decision == "Yes":
        yes_votes += weights['hepatologist']
    
    weighted_decision = "Yes" if yes_votes >= 0.5 else "No"
    confidence = yes_votes if weighted_decision == "Yes" else (1.0 - yes_votes)
    
    system_prompt = """You are the AI Transplant Leader Committee Chair, responsible for synthesizing inputs from three specialist agents:
1. AI Hepatologist (weight: 30%)
2. AI Critical Care Physician (weight: 40%)
3. AI Transplant Surgeon (weight: 30%)

Your role is to provide a final weighted analysis and prediction based on the three specialist opinions.
Consider the weighted voting and provide comprehensive reasoning that synthesizes all perspectives."""

    prompt = f"""{system_prompt}

Hepatologist Decision (30% weight):
Decision: {hepatologist.decision if hepatologist else "N/A"}
Reasoning: {hepatologist.reasoning if hepatologist else "N/A"}

Critical Care Physician Decision (40% weight):
Decision: {critical_care.decision if critical_care else "N/A"}
Reasoning: {critical_care.reasoning if critical_care else "N/A"}

Transplant Surgeon Decision (30% weight):
Decision: {transplant_surgeon.decision if transplant_surgeon else "N/A"}
Reasoning: {transplant_surgeon.reasoning if transplant_surgeon else "N/A"}

Weighted Analysis:
- Critical Care: {weights['critical_care']*100}% weight → {critical_care.decision if critical_care else "N/A"}
- Transplant Surgeon: {weights['transplant_surgeon']*100}% weight → {transplant_surgeon.decision if transplant_surgeon else "N/A"}
- Hepatologist: {weights['hepatologist']*100}% weight → {hepatologist.decision if hepatologist else "N/A"}
- Weighted Score: {yes_votes:.2f} (threshold: 0.50)
- Weighted Decision: {weighted_decision}

Provide your final synthesis and prediction."""

    try:
        client, deployment_name = get_azure_openai_client()
        
        # Use JSON mode for structured output
        json_schema = FinalPrediction.model_json_schema()
        json_prompt = f"""{prompt}

Please respond with a JSON object matching this schema:
{json_schema}

Return only valid JSON, no additional text."""
        
        completion = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=16384,
        )
        
        response_text = completion.choices[0].message.content
        response_json = json.loads(response_text)
        prediction = FinalPrediction(**response_json)
        
        # Override with calculated values
        prediction.prediction = weighted_decision
        prediction.confidence = confidence
        prediction.hepatologist_decision = f"{hepatologist.decision}: {hepatologist.reasoning}" if hepatologist else "N/A"
        prediction.critical_care_decision = f"{critical_care.decision}: {critical_care.reasoning}" if critical_care else "N/A"
        prediction.transplant_surgeon_decision = f"{transplant_surgeon.decision}: {transplant_surgeon.reasoning}" if transplant_surgeon else "N/A"
        
        state['final_prediction'] = prediction
        logger.info(f"Final prediction: {prediction.prediction} (confidence: {prediction.confidence:.2f})")
        
    except Exception as e:
        logger.error(f"Error in Final Synthesis: {e}")
        # Fallback
        state['final_prediction'] = FinalPrediction(
            prediction=weighted_decision,
            confidence=confidence,
            reasoning=f"Weighted analysis: {yes_votes:.2f} weighted score. Error in LLM synthesis: {str(e)}",
            hepatologist_decision=f"{hepatologist.decision}: {hepatologist.reasoning}" if hepatologist else "N/A",
            critical_care_decision=f"{critical_care.decision}: {critical_care.reasoning}" if critical_care else "N/A",
            transplant_surgeon_decision=f"{transplant_surgeon.decision}: {transplant_surgeon.reasoning}" if transplant_surgeon else "N/A"
        )
    
    return state

def create_multi_agent_graph():
    """Create the LangGraph workflow for multi-agent system.
    
    Architecture:
    1. All three agents run (can be parallel in actual execution)
    2. Final synthesis waits for all agents to complete
    3. Outputs final prediction
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("hepatologist", hepatologist_agent)
    workflow.add_node("critical_care", critical_care_agent)
    workflow.add_node("transplant_surgeon", transplant_surgeon_agent)
    workflow.add_node("final_synthesis", final_synthesis)
    
    # Sequential execution: run all agents, then synthesis
    # In practice, agents can run in parallel via async/threading
    workflow.set_entry_point("hepatologist")
    workflow.add_edge("hepatologist", "critical_care")
    workflow.add_edge("critical_care", "transplant_surgeon")
    workflow.add_edge("transplant_surgeon", "final_synthesis")
    workflow.add_edge("final_synthesis", END)
    
    return workflow.compile()

def process_patient_day(row: pd.Series, graph) -> FinalPrediction:
    """Process a single patient-day through the multi-agent system."""
    state = {
        "subject_id": int(row['subject_id']),
        "day": int(row['day']),
        "hepatologist_vignette": row['hepatologist_vignette'] if pd.notna(row.get('hepatologist_vignette')) else "",
        "critical_care_physician_vignette": row['critical_care_physician_vignette'] if pd.notna(row.get('critical_care_physician_vignette')) else "",
        "transplant_surgeon_vignette": row['transplant_surgeon_vignette'] if pd.notna(row.get('transplant_surgeon_vignette')) else "",
        "hepatologist_output": None,
        "critical_care_output": None,
        "transplant_surgeon_output": None,
        "final_prediction": None
    }
    
    # Run the graph
    final_state = graph.invoke(state)
    
    return final_state['final_prediction']

def main():
    """Main function to run the multi-agent system on clinical vignettes."""
    logger.info("Initializing Multi-Agent System")
    
    # Load clinical vignettes
    input_file = 'clinical_vignettes.xlsx'
    logger.info(f"Loading {input_file}")
    df = pd.read_excel(input_file)
    logger.info(f"Loaded {len(df)} patient-day combinations")
    
    # Create the graph
    logger.info("Creating LangGraph workflow...")
    graph = create_multi_agent_graph()
    
    # Process a sample (first 5 rows for testing)
    logger.info("Processing sample patient-day combinations...")
    sample_size = min(5, len(df))
    results = []
    
    for idx, row in df.head(sample_size).iterrows():
        logger.info(f"\nProcessing Subject {int(row['subject_id'])}, Day {int(row['day'])}")
        try:
            prediction = process_patient_day(row, graph)
            results.append({
                'subject_id': int(row['subject_id']),
                'day': int(row['day']),
                'prediction': prediction.prediction,
                'confidence': prediction.confidence,
                'reasoning': prediction.reasoning,
                'actual_survival': row.get('Spont_Survival21', None)
            })
            logger.info(f"Prediction: {prediction.prediction} (confidence: {prediction.confidence:.2f})")
        except Exception as e:
            logger.error(f"Error processing row {idx}: {e}")
            results.append({
                'subject_id': int(row['subject_id']),
                'day': int(row['day']),
                'prediction': 'Error',
                'confidence': 0.0,
                'reasoning': str(e),
                'actual_survival': row.get('Spont_Survival21', None)
            })
    
    # Save results
    results_df = pd.DataFrame(results)
    output_file = 'agent_predictions.xlsx'
    results_df.to_excel(output_file, index=False, engine='openpyxl')
    logger.info(f"\nSaved predictions to {output_file}")
    logger.info(f"\nResults summary:")
    print(results_df)

if __name__ == '__main__':
    main()


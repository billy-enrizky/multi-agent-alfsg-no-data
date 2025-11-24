import os
import json
import logging
import argparse
import pandas as pd
from typing import Literal, TypedDict, Optional, Union
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from openai import OpenAI
from anthropic import AnthropicFoundry, transform_schema
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Pydantic models for structured outputs
class AgentDecision(BaseModel):
    """Individual agent decision output."""
    decision: Literal["Yes", "No"] = Field(description="Prediction: Will patient survive 21 days? Yes or No")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Detailed clinical reasoning for the decision")

class FinalPrediction(BaseModel):
    """Final committee prediction output."""
    prediction: Literal["Yes", "No"] = Field(description="Final prediction: Will patient survive 21 days? Yes or No")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Synthesis of all agent inputs with weighted analysis")

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
    """Initialize client (OpenAI or Anthropic Foundry) based on deployment name."""
    endpoint = os.getenv("ENDPOINT_URL")
    deployment_name = os.getenv("DEPLOYMENT_NAME")
    
    if not endpoint:
        raise ValueError("ENDPOINT_URL environment variable is required")
    if not deployment_name:
        raise ValueError("DEPLOYMENT_NAME environment variable is required")
    
    # Check if using Anthropic Foundry
    if deployment_name == "claude-opus-4-1":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required for Anthropic Foundry")
        client = AnthropicFoundry(
            api_key=api_key,
            base_url=endpoint
        )
        return client, deployment_name, "anthropic"
    else:
        # Default to OpenAI
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")
        client = OpenAI(
            base_url=f"{endpoint}",
            api_key=api_key
        )
        return client, deployment_name, "openai"


def call_llm(client, client_type: str, deployment_name: str, system_prompt: str, user_prompt: str, json_mode: bool = False, json_schema_model=None):
    """Unified function to call either OpenAI or Anthropic API.
    
    Args:
        client: The client instance (OpenAI or AnthropicFoundry)
        client_type: "openai" or "anthropic"
        deployment_name: Model/deployment name
        system_prompt: System prompt
        user_prompt: User prompt
        json_mode: Whether to request JSON output
        json_schema_model: Pydantic model for JSON schema (AgentDecision or FinalPrediction)
    
    Returns:
        For Anthropic with json_mode=True and json_schema_model: Returns the parsed Pydantic model directly
        Otherwise: Returns response text as string
    """
    if client_type == "anthropic":
        # Check if using claude-opus-4-1 and enable extended thinking
        use_thinking = (deployment_name == "claude-opus-4-1")
        
        # Anthropic API - Use native structured outputs when available
        if json_mode and json_schema_model:
            try:
                # Use beta.messages.parse() for native structured outputs (returns parsed Pydantic model directly)
                parse_kwargs = {
                    "model": deployment_name,
                    "max_tokens": 16384,  # Must be > thinking.budget_tokens (10000)
                    "betas": ["structured-outputs-2025-11-13"],
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ],
                    "output_format": json_schema_model,
                }
                
                # Add thinking parameter for claude-opus-4-1
                if use_thinking:
                    parse_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": 10000
                    }
                
                response = client.beta.messages.parse(**parse_kwargs)
                # Return the parsed Pydantic model directly
                return response.parsed_output
            except Exception as e:
                logger.warning(f"Anthropic structured outputs failed, falling back to manual parsing: {e}")
                # Fallback to manual JSON parsing
                json_schema = json_schema_model.model_json_schema()
                
                # Determine the correct field name based on the model
                # AgentDecision uses "decision", FinalPrediction uses "prediction"
                if json_schema_model == FinalPrediction:
                    decision_field = "prediction"
                else:
                    decision_field = "decision"
                
                user_prompt = f"""{user_prompt}

You must respond with a JSON object containing these exact fields:
- "{decision_field}": either "Yes" or "No" (string)
- "confidence": a number between 0.0 and 1.0 (float)
- "reasoning": a detailed explanation (string)

Example JSON format:
{{
  "{decision_field}": "Yes",
  "confidence": 0.85,
  "reasoning": "Your detailed reasoning here"
}}

Full JSON schema for reference:
{json.dumps(json_schema, indent=2)}

Return only valid JSON, no additional text."""
        
        # Regular message creation (for non-JSON mode or fallback)
        create_kwargs = {
            "model": deployment_name,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 16384,  # Must be > thinking.budget_tokens (10000)
        }
        
        # Add thinking parameter for claude-opus-4-1
        if use_thinking:
            create_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 10000
            }
        
        message = client.messages.create(**create_kwargs)
        
        # Extract text from Anthropic response (list of content blocks)
        if not message.content:
            logger.error("Anthropic response has no content")
            return ""
        
        # Handle different content block types (including thinking blocks)
        response_text = ""
        for block in message.content:
            # Handle thinking blocks (extended thinking feature)
            if hasattr(block, 'type'):
                if block.type == "thinking":
                    # Thinking blocks contain summarized thinking - we can log but don't include in response
                    if hasattr(block, 'thinking'):
                        logger.debug(f"Thinking summary: {block.thinking}")
                    continue
                elif block.type == "text":
                    if hasattr(block, 'text'):
                        response_text += block.text
                    continue
            # Fallback for other block types
            if hasattr(block, 'text'):
                response_text += block.text
            elif isinstance(block, dict) and 'text' in block:
                response_text += block['text']
            elif isinstance(block, str):
                response_text += block
        
        if not response_text:
            logger.error(f"Anthropic response content is empty. Content structure: {message.content}")
            return ""
        
        # Extract JSON from markdown code blocks if present (Anthropic often wraps JSON in ```json ... ```)
        response_text = response_text.strip()
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end > start:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            # Handle generic code blocks
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end > start:
                response_text = response_text[start:end].strip()
        
        return response_text
    else:
        # OpenAI API
        if json_mode:
            # OpenAI requires the word "json" in messages when using response_format={"type": "json_object"}
            if json_schema_model:
                # Get the properties we need, not the full schema
                json_schema = json_schema_model.model_json_schema()
                # Extract just the properties we need
                properties = json_schema.get('properties', {})
                
                # Determine the correct field name based on the model
                # AgentDecision uses "decision", FinalPrediction uses "prediction"
                if json_schema_model == FinalPrediction:
                    decision_field = "prediction"
                else:
                    decision_field = "decision"
                
                user_prompt_with_json = f"""{user_prompt}

You must respond with a JSON object containing these exact fields:
- "{decision_field}": either "Yes" or "No" (string)
- "confidence": a number between 0.0 and 1.0 (float)
- "reasoning": a detailed explanation (string)

Example JSON format:
{{
  "{decision_field}": "Yes",
  "confidence": 0.85,
  "reasoning": "Your detailed reasoning here"
}}

Return only the JSON object, no additional text or explanation."""
            else:
                # Ensure "json" is in the prompt
                user_prompt_with_json = f"""{user_prompt}

Please respond with a valid JSON object. Return only JSON, no additional text."""
            
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt_with_json}
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=16384,
            )
        else:
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=16384,
            )
        
        response_text = completion.choices[0].message.content
        return response_text

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

Provide a clear decision (Yes or No), a confidence score (0.0 to 1.0) indicating how certain you are of this prediction, and detailed clinical reasoning."""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    try:
        client, deployment_name, client_type = get_azure_openai_client()
        
        # Try JSON mode first
        response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=AgentDecision)
        
        # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
        if isinstance(response, AgentDecision):
            decision = response
        else:
            # Response is a string, need to parse it
            response_text = response
            if not response_text or not response_text.strip():
                logger.error(f"Empty response from LLM. Client type: {client_type}")
                raise ValueError("Empty response from LLM")
            
            # Try to extract JSON from response (in case there's extra text)
            response_text = response_text.strip()
            
            # Try to find JSON object in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                response_text = response_text[json_start:json_end]
            else:
                logger.warning(f"No JSON object found in response. Full response: {response_text[:1000]}")
            
            try:
                response_json = json.loads(response_text)
                # Validate that we have the required fields before creating the model
                required_fields = ['decision', 'confidence', 'reasoning']
                if not all(field in response_json for field in required_fields):
                    logger.error(f"Missing required fields in JSON response. Got: {list(response_json.keys())}")
                    logger.error(f"Full response text: {response_text[:2000]}")
                    raise ValueError(f"JSON response missing required fields. Expected: {required_fields}, Got: {list(response_json.keys())}")
                
                decision = AgentDecision(**response_json)
            except Exception as parse_error:
                logger.error(f"Failed to parse JSON response: {parse_error}")
                logger.error(f"Response text (first 2000 chars): {response_text[:2000]}")
                raise
        
        state['hepatologist_output'] = decision
        logger.info(f"Hepatologist decision: {decision.decision}")
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in Hepatologist agent: {e}")
        logger.error(f"Response text that failed to parse: {response[:1000] if isinstance(response, str) else 'N/A'}")
        raise
    except Exception as e:
        logger.error(f"Error in Hepatologist agent: {e}")
        # Fallback to basic completion
        try:
            client, deployment_name, client_type = get_azure_openai_client()
            response_text = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=False)
            # Parse response manually
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            # Extract confidence if mentioned, otherwise default to 0.7
            confidence_val = 0.7
            if "confidence" in response_text.lower():
                import re
                conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                if conf_match:
                    try:
                        confidence_val = float(conf_match.group(1))
                        if confidence_val > 1.0:
                            confidence_val = confidence_val / 100.0
                        confidence_val = max(0.0, min(1.0, confidence_val))
                    except:
                        pass
            state['hepatologist_output'] = AgentDecision(
                decision=decision_val,
                confidence=confidence_val,
                reasoning=response_text
            )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            state['hepatologist_output'] = AgentDecision(
                decision="No",
                confidence=0.0,
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

Provide a clear decision (Yes or No), a confidence score (0.0 to 1.0) indicating how certain you are of this prediction, and detailed clinical reasoning."""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    try:
        client, deployment_name, client_type = get_azure_openai_client()
        
        # Try JSON mode first
        response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=AgentDecision)
        
        # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
        if isinstance(response, AgentDecision):
            decision = response
        else:
            # Response is a string, need to parse it
            response_text = response
            if not response_text or not response_text.strip():
                logger.error(f"Empty response from LLM. Client type: {client_type}")
                raise ValueError("Empty response from LLM")
            
            # Try to extract JSON from response (in case there's extra text)
            response_text = response_text.strip()
            
            # Try to find JSON object in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                response_text = response_text[json_start:json_end]
            else:
                logger.warning(f"No JSON object found in response. Full response: {response_text[:1000]}")
            
            try:
                response_json = json.loads(response_text)
                # Validate that we have the required fields before creating the model
                required_fields = ['decision', 'confidence', 'reasoning']
                if not all(field in response_json for field in required_fields):
                    logger.error(f"Missing required fields in JSON response. Got: {list(response_json.keys())}")
                    logger.error(f"Full response text: {response_text[:2000]}")
                    raise ValueError(f"JSON response missing required fields. Expected: {required_fields}, Got: {list(response_json.keys())}")
                
                decision = AgentDecision(**response_json)
            except Exception as parse_error:
                logger.error(f"Failed to parse JSON response: {parse_error}")
                logger.error(f"Response text (first 2000 chars): {response_text[:2000]}")
                raise
        
        state['critical_care_output'] = decision
        logger.info(f"Critical Care decision: {decision.decision}")
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in Critical Care agent: {e}")
        logger.error(f"Response text that failed to parse: {response[:1000] if isinstance(response, str) else 'N/A'}")
        raise
    except Exception as e:
        logger.error(f"Error in Critical Care agent: {e}")
        try:
            client, deployment_name, client_type = get_azure_openai_client()
            response_text = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=False)
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            # Extract confidence if mentioned, otherwise default to 0.7
            confidence_val = 0.7
            if "confidence" in response_text.lower():
                import re
                conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                if conf_match:
                    try:
                        confidence_val = float(conf_match.group(1))
                        if confidence_val > 1.0:
                            confidence_val = confidence_val / 100.0
                        confidence_val = max(0.0, min(1.0, confidence_val))
                    except:
                        pass
            state['critical_care_output'] = AgentDecision(
                decision=decision_val,
                confidence=confidence_val,
                reasoning=response_text
            )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            state['critical_care_output'] = AgentDecision(
                decision="No",
                confidence=0.0,
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

Provide a clear decision (Yes or No), a confidence score (0.0 to 1.0) indicating how certain you are of this prediction, and detailed clinical reasoning."""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    try:
        client, deployment_name, client_type = get_azure_openai_client()
        
        # Try JSON mode first
        response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=AgentDecision)
        
        # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
        if isinstance(response, AgentDecision):
            decision = response
        else:
            # Response is a string, need to parse it
            response_text = response
            if not response_text or not response_text.strip():
                logger.error(f"Empty response from LLM. Client type: {client_type}")
                raise ValueError("Empty response from LLM")
            
            # Try to extract JSON from response (in case there's extra text)
            response_text = response_text.strip()
            
            # Try to find JSON object in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                response_text = response_text[json_start:json_end]
            else:
                logger.warning(f"No JSON object found in response. Full response: {response_text[:1000]}")
            
            try:
                response_json = json.loads(response_text)
                # Validate that we have the required fields before creating the model
                required_fields = ['decision', 'confidence', 'reasoning']
                if not all(field in response_json for field in required_fields):
                    logger.error(f"Missing required fields in JSON response. Got: {list(response_json.keys())}")
                    logger.error(f"Full response text: {response_text[:2000]}")
                    raise ValueError(f"JSON response missing required fields. Expected: {required_fields}, Got: {list(response_json.keys())}")
                
                decision = AgentDecision(**response_json)
            except Exception as parse_error:
                logger.error(f"Failed to parse JSON response: {parse_error}")
                logger.error(f"Response text (first 2000 chars): {response_text[:2000]}")
                raise
        
        state['transplant_surgeon_output'] = decision
        logger.info(f"Transplant Surgeon decision: {decision.decision}")
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in Transplant Surgeon agent: {e}")
        logger.error(f"Response text that failed to parse: {response[:1000] if isinstance(response, str) else 'N/A'}")
        raise
    except Exception as e:
        logger.error(f"Error in Transplant Surgeon agent: {e}")
        try:
            client, deployment_name, client_type = get_azure_openai_client()
            response_text = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=False)
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            # Extract confidence if mentioned, otherwise default to 0.7
            confidence_val = 0.7
            if "confidence" in response_text.lower():
                import re
                conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                if conf_match:
                    try:
                        confidence_val = float(conf_match.group(1))
                        if confidence_val > 1.0:
                            confidence_val = confidence_val / 100.0
                        confidence_val = max(0.0, min(1.0, confidence_val))
                    except:
                        pass
            state['transplant_surgeon_output'] = AgentDecision(
                decision=decision_val,
                confidence=confidence_val,
                reasoning=response_text
            )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            state['transplant_surgeon_output'] = AgentDecision(
                decision="No",
                confidence=0.0,
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
        client, deployment_name, client_type = get_azure_openai_client()
        
        # Use JSON mode for structured output
        response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=FinalPrediction)
        
        # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
        if isinstance(response, FinalPrediction):
            prediction = response
        else:
            # Response is a string, need to parse it
            response_text = response
            if not response_text or not response_text.strip():
                logger.error(f"Empty response from LLM. Client type: {client_type}")
                raise ValueError("Empty response from LLM")
            
            # Try to extract JSON from response (in case there's extra text)
            response_text = response_text.strip()
            
            # Try to find JSON object in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                response_text = response_text[json_start:json_end]
            else:
                logger.warning(f"No JSON object found in response. Full response: {response_text[:1000]}")
            
            response_json = json.loads(response_text)
            
            # Handle case where LLM returns "decision" instead of "prediction" (for FinalPrediction)
            if "decision" in response_json and "prediction" not in response_json:
                logger.warning("LLM returned 'decision' instead of 'prediction', converting...")
                response_json["prediction"] = response_json.pop("decision")
            
            prediction = FinalPrediction(**response_json)
        
        # Override with calculated values
        prediction.prediction = weighted_decision
        prediction.confidence = confidence
        
        state['final_prediction'] = prediction
        logger.info(f"Final prediction: {prediction.prediction} (confidence: {prediction.confidence:.2f})")
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in Final Synthesis: {e}")
        logger.error(f"Response text that failed to parse: {response[:1000] if isinstance(response, str) else 'N/A'}")
        # Fallback
        state['final_prediction'] = FinalPrediction(
            prediction=weighted_decision,
            confidence=confidence,
            reasoning=f"Weighted analysis: {yes_votes:.2f} weighted score. JSON parse error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in Final Synthesis: {e}")
        # Fallback
        state['final_prediction'] = FinalPrediction(
            prediction=weighted_decision,
            confidence=confidence,
            reasoning=f"Weighted analysis: {yes_votes:.2f} weighted score. Error in LLM synthesis: {str(e)}"
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

def process_patient_day(row: pd.Series, graph) -> dict:
    """Process a single patient-day through the multi-agent system.
    
    Returns a dictionary with:
    - final_prediction: FinalPrediction object
    - hepatologist_output: AgentDecision object
    - critical_care_output: AgentDecision object
    - transplant_surgeon_output: AgentDecision object
    """
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
    
    return {
        'final_prediction': final_state['final_prediction'],
        'hepatologist_output': final_state['hepatologist_output'],
        'critical_care_output': final_state['critical_care_output'],
        'transplant_surgeon_output': final_state['transplant_surgeon_output']
    }

def main():
    """Main function to run the multi-agent system on clinical vignettes."""
    parser = argparse.ArgumentParser(description='Multi-Agent System for Clinical Vignette Predictions')
    parser.add_argument('--num_patient', type=int, default=None,
                        help='Number of patients to process (default: all patients)')
    parser.add_argument('--day', type=int, default=None,
                        help='Specific day to process (default: maximum day for each patient)')
    
    args = parser.parse_args()
    
    logger.info("Initializing Multi-Agent System")
    
    # Load clinical vignettes
    input_file = 'clinical_vignettes.xlsx'
    logger.info(f"Loading {input_file}")
    df = pd.read_excel(input_file)
    logger.info(f"Loaded {len(df)} patient-day combinations")
    
    # Filter by day: if day is None, use maximum day for each patient
    # If day < 1, use day 1 for each patient
    # If day > maximum day for a patient, use maximum day for that patient
    max_day_per_patient = df.groupby('subject_id')['day'].max().reset_index()
    max_day_per_patient.columns = ['subject_id', 'max_day']
    df = df.merge(max_day_per_patient, on='subject_id')
    
    if args.day is None:
        logger.info("No specific day provided, filtering to maximum day for each patient")
        df = df[df['day'] == df['max_day']].drop(columns=['max_day'])
        logger.info(f"Filtered to maximum day per patient: {len(df)} patient-day combinations")
    else:
        # Determine target day for each patient based on specified day
        # If specified_day < 1, use day 1; if specified_day > max_day, use max_day; otherwise use specified_day
        # Formula: target_day = max(1, min(specified_day, max_day))
        logger.info(f"Specified day: {args.day}")
        
        # For each patient, determine the actual target day
        df['target_day'] = df.apply(
            lambda row: max(1, min(args.day, row['max_day'])),
            axis=1
        )
        
        # Filter to keep only rows where day matches the target day
        df = df[df['day'] == df['target_day']].drop(columns=['max_day', 'target_day'])
        logger.info(f"Filtered to target day per patient (specified: {args.day}, clamped to [1, max_day] per patient): {len(df)} patient-day combinations")
    
    # Filter by number of patients if specified
    if args.num_patient is not None:
        unique_patients = df['subject_id'].unique()[:args.num_patient]
        df = df[df['subject_id'].isin(unique_patients)]
        logger.info(f"Filtered to {args.num_patient} patients: {len(df)} patient-day combinations")
    
    if len(df) == 0:
        logger.warning("No patient-day combinations to process after filtering")
        return
    
    # Create the graph
    logger.info("Creating LangGraph workflow...")
    graph = create_multi_agent_graph()
    
    # Process all filtered patient-day combinations
    logger.info(f"Processing {len(df)} patient-day combinations...")
    results = []
    
    for idx, row in df.iterrows():
        logger.info(f"\nProcessing Subject {int(row['subject_id'])}, Day {int(row['day'])}")
        try:
            outputs = process_patient_day(row, graph)
            final_pred = outputs['final_prediction']
            hepatologist = outputs['hepatologist_output']
            critical_care = outputs['critical_care_output']
            transplant_surgeon = outputs['transplant_surgeon_output']
            
            results.append({
                'subject_id': int(row['subject_id']),
                'day': int(row['day']),
                'final_prediction': final_pred.prediction if final_pred else None,
                'final_confidence': final_pred.confidence if final_pred else None,
                'final_reasoning': final_pred.reasoning if final_pred else None,
                'hepatologist_decision': hepatologist.decision if hepatologist else None,
                'hepatologist_confidence': hepatologist.confidence if hepatologist else None,
                'hepatologist_reasoning': hepatologist.reasoning if hepatologist else None,
                'critical_care_decision': critical_care.decision if critical_care else None,
                'critical_care_confidence': critical_care.confidence if critical_care else None,
                'critical_care_reasoning': critical_care.reasoning if critical_care else None,
                'transplant_surgeon_decision': transplant_surgeon.decision if transplant_surgeon else None,
                'transplant_surgeon_confidence': transplant_surgeon.confidence if transplant_surgeon else None,
                'transplant_surgeon_reasoning': transplant_surgeon.reasoning if transplant_surgeon else None,
                'actual_survival': row.get('Spont_Survival21', None)
            })
            logger.info(f"Final Prediction: {final_pred.prediction if final_pred else 'N/A'} (confidence: {final_pred.confidence if final_pred else 0.0:.2f})")
        except Exception as e:
            logger.error(f"Error processing row {idx}: {e}")
            results.append({
                'subject_id': int(row['subject_id']),
                'day': int(row['day']),
                'final_prediction': 'Error',
                'final_confidence': 0.0,
                'final_reasoning': str(e),
                'hepatologist_decision': None,
                'hepatologist_confidence': None,
                'hepatologist_reasoning': None,
                'critical_care_decision': None,
                'critical_care_confidence': None,
                'critical_care_reasoning': None,
                'transplant_surgeon_decision': None,
                'transplant_surgeon_confidence': None,
                'transplant_surgeon_reasoning': None,
                'actual_survival': row.get('Spont_Survival21', None)
            })
    
    # Always save results to Excel file
    results_df = pd.DataFrame(results)
    output_file = 'agent_predictions.xlsx'
    results_df.to_excel(output_file, index=False, engine='openpyxl')
    logger.info(f"\nSaved predictions to {output_file}")
    logger.info(f"\nResults summary:")
    logger.info(f"Total predictions: {len(results_df)}")
    logger.info(f"Results saved to {output_file}")
    print(results_df)

if __name__ == '__main__':
    main()


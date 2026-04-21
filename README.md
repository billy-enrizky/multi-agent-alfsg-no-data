# Multi-agent-alfsg

Multi-Agent AI Transplant Committee for predicting 21-day transplant-free survival in acute liver failure (ALF), using the ALFSG registry.

## Demo

https://github.com/user-attachments/assets/da12745b-465e-4377-92f4-e030e6d3a2fe

## Repository Structure

```
multi-agent-alfsg/
  multi_agent_system.py            # Main multi-agent prediction system
  create_vignettes.py              # Generates clinical vignettes from raw ALFSG data
  create_agent_variable_mapping.py # Creates agent-to-variable mapping table
  create_label_legend.py           # Creates label legend for vignette categorical encoding
  process_excel.py                 # Excel data processing utilities
  streamlit_app.py                 # Streamlit web app for interactive predictions
  STREAMLIT_README.md              # Streamlit app documentation
  pyproject.toml                   # Python project config and dependencies
  uv.lock                          # Dependency lock file
  package.json                     # Node.js dependencies
  .devcontainer/devcontainer.json  # Dev container configuration
```

## Setup

```bash
# Install dependencies
uv sync

# Set up environment variables (Azure OpenAI credentials)
cp .env.example .env
# Edit .env with your endpoint URL and API key

# Run predictions
uv run multi_agent_system.py --num_patient 100 --deployment gpt-5.2

# Run predictions for specific patients
uv run multi_agent_system.py --patient_id 1279 1101 1536 --deployment gpt-5.2

# Launch Streamlit app
uv run streamlit run streamlit_app.py
```

# Streamlit App - Multi-Agent ALFSG Predictor

## Quick Start

Run the Streamlit app with:

```bash
uv run streamlit run streamlit_app.py
```

Or if you have streamlit installed globally:

```bash
streamlit run streamlit_app.py
```

The app will automatically open in your browser at `http://localhost:8501`

## Features

### Input
- **Automatic Data Loading**: Loads `clinical_vignettes.xlsx` automatically
- **Patient Selection**: Dropdown to select from all available patient IDs
- **Day Selection**: Dropdown filtered by selected patient showing available days
- **One-Click Prediction**: Single "Predict Survival" button to run the multi-agent system

### Output
- **Clinical Vignettes**: Displays the vignette text for each agent (Hepatologist, Critical Care Physician, Transplant Surgeon)
- **Agent Decisions**: Shows each agent's:
  - Decision (Yes/No) with color coding
  - Confidence score (as percentage) with color coding (high/medium/low)
  - Detailed reasoning
- **Final Prediction**: Displays the committee's final decision with:
  - Prediction (Yes/No) in large, prominent display
  - Confidence score
  - Comprehensive reasoning
  - Weighted voting breakdown showing each agent's contribution

### UI Features
- Beautiful gradient styling
- Color-coded confidence scores
- Responsive 3-column layout
- Patient information sidebar
- Dataset statistics
- Loading spinner during prediction

## Requirements

- `clinical_vignettes.xlsx` must be in the same directory
- Environment variables set:
  - `ENDPOINT_URL`: Azure OpenAI endpoint
  - `AZURE_OPENAI_API_KEY`: API key for authentication

## Usage

1. Select a patient ID from the dropdown
2. Select a day from the filtered day dropdown
3. Click "🔮 Predict Survival"
4. Wait for the multi-agent system to process (may take 1-2 minutes)
5. Review the results:
   - Clinical vignettes for each agent
   - Individual agent decisions and reasoning
   - Final committee prediction


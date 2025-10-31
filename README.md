# Multi-agent-alfsg
Multi Agent AI Transplant Committee for ALFSG project

## Mermaid Diagram

```mermaid
graph TD;
    A[Raw Patient Data] --> B{Preprocessing Engine};
    B -- "1. Bin Continuous (e.g., Lactate: 10.5 -> 'Critical')" --> C[Processed Qualitative Data];
    B -- "2. Label Categorical (e.g., Trt_Pressors: 1 -> 'Yes')" --> C;
    
    C --> D(Data Router);

    subgraph "🤖 Parallel Multi-Agent AI Committee"
        direction: TD
        D -- "Hepato Vars" --> E[AI Hepatologist];
        D -- "ICU Vars" --> F[AI Critical Care Physician];
        D -- "Surgical/MELD Vars" --> G[AI Transplant Surgeon];
        D -- "Etiology Vars" --> H[AI Psychiatrist];
        D -- "Demographic Vars" --> I[AI Social Worker];

        E --> E_out(Hepatologist Output \n Decision: ... \n Reasoning: ...);
        F --> F_out(Critical Care Output \n Decision: ... \n Reasoning: ...);
        G --> G_out(Surgeon Output \n Decision: ... \n Reasoning: ...);
        H --> H_out(Psychiatrist Output \n Decision: ... \n Reasoning: ...);
        I --> I_out(Social Worker Output \n Decision: ... \n Reasoning: ...);
    end

    subgraph "⚖️ Final Synthesis"
        E_out --> J[AI Transplant Leader Committee];
        F_out --> J;
        G_out --> J;
        H_out --> J;
        I_out --> J;
        
        J -- "Applies weighting logic \n (e.g., Critical Care=30%, Surgeon=30%)" --> K(Weighted Analysis);
    end

    K --> L[🏆 Final Recommendation \n (e.g., 'Category 2: Urgent LT')];

    %% Styling
    style A fill:#fbe9e7,stroke:#c8b7b5,stroke-width:2px
    style B fill:#e3f2fd,stroke:#b1c5d4,stroke-width:2px
    style C fill:#e8f5e9,stroke:#b8c7b9,stroke-width:2px
    style E fill:#fff3e0,stroke:#d3c4b1,stroke-width:2px
    style F fill:#ede7f6,stroke:#c3bdd4,stroke-width:2px
    style G fill:#fbe9e7,stroke:#c8b7b5,stroke-width:2px
    style H fill:#e0f2f1,stroke:#b0c5c4,stroke-width:2px
    style I fill:#fce4ec,stroke:#c9b6bd,stroke-width:2px
    style E_out fill:#fff3e0,stroke:#d3c4b1,stroke-width:2px
    style F_out fill:#ede7f6,stroke:#c3bdd4,stroke-width:2px
    style G_out fill:#fbe9e7,stroke:#c8b7b5,stroke-width:2px
    style H_out fill:#e0f2f1,stroke:#b0c5c4,stroke-width:2px
    style I_out fill:#fce4ec,stroke:#c9b6bd,stroke-width:2px
    style J fill:#42a5f5,stroke:#1e88e5,stroke-width:3px,color:#fff
    style K fill:#42a5f5,stroke:#1e88e5,stroke-width:3px,color:#fff
    style L fill:#4caf50,stroke:#388e3c,stroke-width:4px,color:#fff
```


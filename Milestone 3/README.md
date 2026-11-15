# FreightQuote AI - Milestone 3

## Overview
FreightQuote AI is an agentic quoting and fleet-watch platform for sea freight. This repository contains the deliverables for Milestone 3 of the Infosys Springboard Internship 7.0 (Batch 4).

## How to Run
1. Open the final notebook (`FreightQuote_AI_v5.ipynb`) in **Google Colab**.
2. Ensure the Runtime is set to **T4 GPU**.
3. Set `USE_DRIVE = True` and `PERSIST = True` so data and chats are backed up.
4. Add your ngrok token as a Colab Secret (`NGROK_AUTHTOKEN`).
5. Click **Runtime → Run all** and follow the generated ngrok public link to access the single-page application.

## Roles & Access
The application features Role-Based Access Control (RBAC) with the following roles:
* **Customer**: Requests quotes (origin, destination, cargo, HS code) and views results.
* **Freight Broker**: Handles quotes, customs documents, and resolves tickets.
* **Operations Manager**: Approves re-routes, quote holds, margin reviews, and runs agent cycles.
* **Auditor**: Has a read-only view of the entire system and audit trail.
* **Admin**: Manages everything above, plus the autonomy policy, approval chains, System check, and Teaching the Copilot.

## AI Copilot: SQL and RAG Usage
The conversational AI Copilot uses a multi-layered approach to provide accurate, cited answers:
* **SQL (Exact & Planners)**: Handles queries for exact numbers, counts, "top N" requests, and lane planners using read-only Natural Language to SQL (`analyst.py` and `qa.py`). Every number stated is checked against the SQLite database to prevent hallucinations.
* **RAG (Knowledge Base)**: Uses FAISS vectors, BM25, and a cross-encoder reranker over document chunks to answer questions regarding policies, Incoterms, customs, and shipping documents. Answers include citations (e.g., [1], [2]).

## Knowledge Base: Sources and Chunks Collected
* **150+ Sources Collected**: Built using the `FreightQuoteAI_RAG_Builder_FINAL.ipynb` notebook.
* **Topics Covered**: Includes comprehensive data on Incoterms, customs rules, HS codes, container types, freight rates, demurrage/detention, port congestion, weather risks, and marine insurance.
* **Data Sources**: Publicly scraped websites and PDFs (with personal data strictly excluded).

## 50+ Taught Questions
To cover knowledge gaps, we identified 50+ domain questions the Copilot initially could not answer or gave weak matches for.
* These were added via **Admin → Teach Copilot**. 
* The correct answers and keywords were fed into the system, achieving a 50/50 counter on the Teach page.
* Unfixable intents were added manually to the `INTENTS` list in `copilot_pro.py` and synonyms in `qa.py`. (See `taught_questions.csv` for the full list).

## Agent Simulator Improvements
The simulators for each agent (`sim_fq.py`) were improved to include assumptions, percentile ranges (10th to 90th), seed values for repeatability, and dynamic reads from the database:
* **Route Simulator**: Added canal/strait closures and fuel price changes; configured to compare transit days and costs across three alternative routes.
* **Quote Simulator**: Incorporated margin, fuel, and exchange-rate fluctuations; now displays a price band and the probability of winning the quote.
* **Carrier Simulator**: Factored in on-time reliability and capacity shortages to better rank carriers during disruptions.
* **Weather Simulator**: Added variables for storm intensity and duration to estimate delay days and potential demurrage costs.
* **Customs Simulator**: Integrated inspection rates and missing-document delays to calculate holding costs per day.

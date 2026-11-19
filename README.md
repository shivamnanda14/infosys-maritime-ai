FREIGHTQUOTE AI

# Project Documentation

Condensed from 34 original sections into 25 topics --- key
implementation details retained

## 1. Project Overview, Problem Statement and Objectives

FreightQuote AI is an AI-powered maritime freight management and
decision-support platform designed to improve freight pricing, maritime
route planning, shipment monitoring, and operational risk management. It
combines specialized AI agents, machine-learning models, route
calculations, weather information, five freight simulators, Monte Carlo
analysis, a Digital Twin, and an AI Copilot.

Maritime freight operations face fluctuating freight prices caused by
fuel costs, carrier rates, exchange rates, port charges, and market
conditions. Storms, closed maritime passages, congestion, and
geopolitical disruptions can make routes unsuitable. Weather can
increase transit time and demurrage; carrier outages can create capacity
shortages; customs inspections and missing documents can delay
clearance. A single estimated cost also fails to represent the range of
possible outcomes under uncertain conditions. Relevant maritime policies
and regulations are distributed across websites and PDF documents,
making information retrieval difficult.

FreightQuote AI addresses these challenges through coordinated agents,
data-driven predictions, configurable scenario simulations, uncertainty
analysis, a Digital Twin, and document-based knowledge retrieval.

### Objectives

-   Automate important stages of maritime freight quote evaluation and
    identify suitable routes.
-   Estimate freight prices using machine learning and operational cost
    factors.
-   Monitor weather, congestion, carrier, customs, and documentation
    risks.
-   Detect unusual freight quote patterns and evaluate the financial
    impact of disruptions.
-   Enhance simulators with database-driven inputs, editable
    assumptions, and uncertainty ranges.
-   Test hypothetical system-wide changes without modifying live
    operational data.
-   Build a searchable maritime knowledge base and provide SQL- and
    RAG-based Copilot answers.
-   Support human review, role-based permissions, approvals, and audit
    tracking.

### Project notebooks

  -----------------------------------------------------------------------
  Notebook                            Responsibility
  ----------------------------------- -----------------------------------
  FreightQuote AI Main Application    Freight operations, agents,
                                      database, simulators, Digital Twin,
                                      and Copilot.

  FreightQuote AI RAG Builder         Website crawling, PDF discovery,
                                      extraction, chunking, indexing,
                                      retrieval evaluation, and
                                      knowledge-base export.
  -----------------------------------------------------------------------

## 2. Key Features and Overall System Architecture

-   Agentic freight quoting with seven specialized quote-processing
    agents.
-   Maritime route optimization using a sea-navigation graph and
    Dijkstra-based navigation.
-   Machine-learning-based freight pricing and congestion prediction.
-   Weather and customs risk assessment, carrier monitoring, and quote
    anomaly detection.
-   Five enhanced simulators: Route, Quote, Carrier, Weather, and
    Customs.
-   Monte Carlo uncertainty and sensitivity analysis, plus Digital Twin
    what-if testing.
-   AI Copilot with structured SQL question answering and document-based
    RAG.
-   Role-based access, human approval workflows, alerts, reports, and
    audit records.

### Layered architecture

  -----------------------------------------------------------------------
  Layer                               Implementation and responsibility
  ----------------------------------- -----------------------------------
  Frontend                            HTML, CSS, JavaScript; single-page,
                                      server-driven interface with
                                      dashboards, maps, charts, forms,
                                      simulators, Copilot, approvals, and
                                      reports.

  Backend                             Python, FastAPI, and Uvicorn; API
                                      requests, freight processing, agent
                                      execution, database operations,
                                      simulations, Digital Twin,
                                      authentication, and reporting.

  Agent orchestration                 LangGraph organizes agent
                                      execution, conditional transitions,
                                      and replanning.

  Data                                SQLite stores shipments, quotes,
                                      rates, ports, carriers, vessels,
                                      customers, customs rules, weather,
                                      agent runs, approvals, audit
                                      records, Copilot data, and
                                      scenarios.

  AI and knowledge                    Scikit-learn models,
                                      Qwen2.5-Instruct, embeddings, BM25,
                                      FAISS, reranking, and Monte Carlo
                                      analysis.
  -----------------------------------------------------------------------

## 3. Technology Stack

  -----------------------------------------------------------------------
  Category                            Technologies / purpose
  ----------------------------------- -----------------------------------
  Programming and processing          Python; NumPy, Pandas, SciPy

  Frontend and visualization          HTML, CSS, JavaScript; Apache
                                      ECharts, Plotly, Leaflet

  Backend and server                  FastAPI, Uvicorn

  Agent orchestration                 LangGraph

  Database                            SQLite

  Machine learning                    Scikit-learn

  Route optimization                  Dijkstra-based sea navigation

  Vector and keyword retrieval        FAISS, BM25

  Retrieval fusion and reranking      Reciprocal Rank Fusion (RRF),
                                      cross-encoder

  Language and embedding models       Qwen2.5-Instruct; multilingual
                                      MiniLM-L12

  Translation and documents           NLLB-200; PyMuPDF, pdfplumber,
                                      ReportLab

  Web crawling                        Requests, BeautifulSoup, lxml

  Deployment and acceleration         Google Colab, ngrok, Transformers,
                                      Accelerate, compatible NVIDIA GPU
  -----------------------------------------------------------------------

## 4. Application Workflow and Decision Process

### Freight quote workflow

1.  A customer submits a freight quotation request, which is stored in
    SQLite.
2.  The Route Agent identifies a suitable maritime route.
3.  The Weather Agent evaluates conditions; high weather risk can
    trigger conditional route replanning through LangGraph.
4.  The Pricing Agent predicts the base freight rate and calculates
    applicable costs.
5.  The Customs Agent checks HS codes, customs rules, restrictions, and
    required documents.
6.  The Margin Agent evaluates profitability.
7.  The Document Agent generates shipment documents at the appropriate
    workflow stage; the Alert Agent evaluates results and proposes
    relevant actions.
8.  The decision engine determines whether the quote is Approved,
    Pending Approval, or On Hold; risky actions enter the human approval
    workflow.

### Fleet monitoring workflow

The fleet-monitoring system periodically evaluates route conditions,
weather exposure, customs holds, missing documents, quote status, and
unusual pricing or margin patterns. Watchers generate operational
scores, alerts, and proposed actions. Agent runs, decisions, alerts, and
actions are recorded in the database.

### Decision examples documented in the project

-   Quotes exceeding \$50,000 require Admin approval.
-   Margin below 10% requires review.
-   High weather risk can trigger route replanning.
-   Missing customs documents can place a quote On Hold.
-   The approval workflow follows a four-eyes principle: the person
    requesting an action cannot approve that same action; critical
    actions can require an additional Admin approval.

## 5. Multi-Agent Architecture and Agent Responsibilities

FreightQuote AI contains two distinct groups: seven quote-processing
agents that handle individual freight requests, and five
fleet-monitoring agents that monitor broader operations. They should not
be described as a single workflow.

  -----------------------------------------------------------------------
  Quote agent                         Responsibility
  ----------------------------------- -----------------------------------
  Route Agent                         Uses a sea-lane graph and
                                      Dijkstra-based navigation;
                                      considers origin/destination,
                                      coastlines, canals, straits, closed
                                      passages, route distance, and
                                      estimated duration.

  Weather Agent                       Uses Open-Meteo forecast and marine
                                      APIs; evaluates wind, wave height,
                                      temperature, precipitation, and
                                      severity. The implementation
                                      samples five route points; high
                                      risk can trigger replanning.

  Pricing Agent                       Uses a Random Forest Regressor to
                                      estimate the base freight rate per
                                      lane; considers route distance,
                                      cargo weight/type, congestion, fuel
                                      surcharge, carrier rates, port
                                      charges, and other applicable
                                      costs.

  Customs Agent                       Checks HS code chapter, customs
                                      rules, restricted goods, required
                                      documents, and attached documents;
                                      identifies missing documentation
                                      and possible holds.

  Margin Agent                        Evaluates quote profitability using
                                      estimated cost, selling price, and
                                      target margin; customer tier
                                      influences target margin.

  Document Agent                      Uses ReportLab to generate shipment
                                      PDFs such as Bill of Lading and
                                      Packing List.

  Alert Agent                         Evaluates agent results and
                                      operational conditions; generates
                                      alerts and proposes actions such as
                                      review, approval, or replanning.
  -----------------------------------------------------------------------

### Margin calculation

The documented selling-price formula is P = C / (1 − M), where P is
selling price, C is total estimated cost, and M is target margin
expressed as a fraction.

### Weather data note

Weather data is cached and stored in the wx_live table. Stored or
simulated weather-risk data can be used as a fallback when external
retrieval is unavailable.

## 6. Fleet Monitoring System

  -----------------------------------------------------------------------
  Fleet watcher                       Responsibility
  ----------------------------------- -----------------------------------
  Route Watcher                       Monitors route-related operational
                                      conditions.

  Weather Watcher                     Identifies vessels exposed to high
                                      weather risk.

  Customs Watcher                     Monitors customs holds and missing
                                      documentation.

  Quote Watcher                       Tracks pending and held freight
                                      quotes.

  Anomaly Watcher                     Detects unusual quote and margin
                                      patterns using Isolation Forest.
  -----------------------------------------------------------------------

The configured fleet cycle runs approximately every 60 seconds. The
fleet system produces operational scores, alerts, and proposed actions
for the Command Center. The Anomaly Watcher uses features such as
price-to-base-cost ratio, margin, and fuel share.

## 7. Machine Learning Models and Algorithms

  -----------------------------------------------------------------------
  Model / algorithm                   Application
  ----------------------------------- -----------------------------------
  Random Forest Regressor             Predicts base freight rates per
                                      lane.

  Random Forest Classifier            Predicts port congestion.

  Isolation Forest                    Detects unusual freight quote
                                      patterns.

  Dijkstra's algorithm                Calculates suitable maritime routes
                                      through the sea-navigation graph.

  Monte Carlo simulation              Estimates uncertain operational and
                                      financial outcomes.
  -----------------------------------------------------------------------

The Random Forest models use scikit-learn. Models are specialist
components coordinated by agents and business logic; the language model
does not independently determine every operational prediction or
numerical freight price.

## 8. Five Enhanced Freight Simulators --- Common Design

The five simulators evaluate distinct operational scenarios. Their
principal functions are in sim_fq.py. The shared Monte Carlo
calculations are in mc_sims.py, and shared visualization functions are
in mc.py.

1.  Retrieve relevant operational starting values from SQLite.
2.  Accept user-selected scenario assumptions through the interface.
3.  Apply the selected scenario to the relevant calculation.
4.  Calculate baseline and modified results.
5.  Generate random samples to represent uncertainty where implemented.
6.  Calculate percentile values and display KPIs, charts, tables, and
    assumptions. The individual simulator functions use NumPy seed 42
    and direct uncertainty calculations generally use 1,000 samples.
    This is distinct from the shared Monte Carlo module, which uses
    1,500 iterations and seed 11.

## 9. Route Simulator

Function: run_route(a). Purpose: evaluate route disruptions and estimate
additional distance, transit time, and cost.

### Inputs and data

-   Closed maritime chokepoints, storm-affected area, wind speed,
    additional congestion, fuel-price change, delay cost per day, and
    number of active lanes.
-   Reads active shipments, groups them by origin-destination lane, and
    retrieves port coordinates, average dwell days, and congestion
    index.

### Processing and outputs

The simulator calculates the baseline route, applies closed chokepoints
or storm constraints, calculates a modified route, and compares
distances and travel days. It estimates additional sailing and delay
costs, generates 1,000 random cost samples, and calculates P10/P90
estimates. Its comparison output can show Route A (baseline), Route B
(scenario), and Route C (a distinct alternative).

### Formulas and assumptions

Vessel speed = 14 knots. Estimated sailing time T = D / (14 × 24), where
D is nautical miles. Base freight rate = \$0.012 per
tonne-nautical-mile; fuel-adjusted rate changes with the fuel input.
Additional distance cost is based on extra distance × rate × weight.
Additional delay cost is additional days × daily delay cost × shipment
count. Total additional cost = distance cost + delay cost.

  Parameter              Configured value
  ---------------------- ---------------------------------
  Vessel speed           14 knots
  Base freight rate      \$0.012 per tonne-nautical-mile
  Delay cost             \$120 per day
  Route cost variation   10% standard deviation
  Fuel slider range      −30% to +80%
  Direct sampling seed   42; 1,000 samples

Outputs include active lanes, rerouted lanes, lanes without a route,
baseline/scenario distances and days, expected additional cost, P10/P90
values, alternative route comparison, and lane-level analysis. Example:
if the Suez Canal is closed, the simulator searches for an alternative
route and estimates extra distance, delay, and cost.

## 10. Quote Simulator

Function: run_quote(a). Purpose: evaluate how operational-cost and
selling-price changes affect freight quote profitability.

### Inputs, data, and processing

Inputs include fuel-price change, carrier-rate change, discount,
foreign-exchange change, price elasticity, and target margin. The
simulator retrieves the latest 400 quotes with positive final prices and
reads quote ID, carrier, base cost, insurance, customs fee, fuel
surcharge, final price, and margin.

It recalculates estimated cost, applies carrier, FX, and fuel changes,
determines pass-through price using the supplied target margin or
current margin, tests selling-price changes from −10% to +20% in 2%
increments, estimates win probability and expected profit, and generates
1,000 random profit variations for each price level. It calculates
P10/P90 profit bands and per-quote P10/P50/P90 price bands.

### Key calculations and assumptions

Estimated current cost: C₀ = P₀(1 − M₀/100). The documented
win-probability model is P(win) = 0.45e\^(−e(P/P₀ − 1)), where e is
price elasticity. Expected profit = P(win) × (P − C₁), with C₁ as
modified cost. The default elasticity is 2.0, initial win probability is
45%, profit variation is 15%, and no target margin is forced unless
supplied. Random seed is 42.

### Outputs

-   Margin if prices are held and if costs are passed through; quotes
    below 5% margin.
-   Best price movement, expected profit, profit distribution, P10/P90
    profit estimates, aggregate P10/P50/P90 price bands, win-probability
    curve, and repricing-priority table. Example: when fuel and carrier
    rates increase, the simulator recalculates quote costs, tests
    selling-price changes, compares expected profit, and displays
    uncertainty bands.

## 11. Carrier Simulator

Function: run_carrier(a). Purpose: evaluate carrier disruption and
reassign affected shipments to alternative carriers.

### Inputs and processing

Inputs include selected carrier, capacity lost, delay cost per day,
on-time reliability adjustment, and alternative-carrier capacity
shortage. The simulator retrieves carrier rating, on-time percentage,
average cost index, risk level, and active shipment details. It applies
capacity loss, adjusts reliability, ranks alternatives, calculates
available capacity, reassigns shipments while capacity remains, and
marks unassigned shipments NO CAPACITY.

### Ranking and assumptions

Carrier score: S = (R/5) × 40 + O × 0.4 − 12C − Pᵣ, where R is rating, O
is on-time percentage, C is average cost index, and Pᵣ is risk penalty.
Risk penalties are Low = 0, Medium = 6, High = 14. Alternative capacity
defaults to 30% of active load and is reduced by any selected shortage.
Delay cost is \$120/day; a one-percentage-point on-time difference
converts to 0.08 days. Delay-cost variation is 10%. Direct sampling uses
1,000 samples and seed 42.

### Outputs

-   Displaced, reassigned, and unplaced shipment counts;
    alternative-carrier ranking and remaining capacity.
-   Additional cost, delay-cost estimate, P90 delay cost, and shipment
    reassignment table. Example: if a carrier loses all capacity,
    affected shipments are identified, alternative carriers are ranked,
    and shipments are reassigned where capacity exists.

## 12. Weather Simulator

Function: run_weather(a). It evaluates a user-specified storm scenario;
it is not itself a storm forecasting model.

### Inputs, supported areas, and processing

Inputs include storm-affected area, wind speed, storm radius, demurrage
per day, and duration. Supported areas include the Red Sea, Arabian Sea,
Strait of Malacca, South China Sea, Bay of Biscay, Cape of Good Hope,
and North Atlantic. Vessel and shipment information and port coordinates
are retrieved. The Haversine formula calculates vessel/port distance
from the storm centre; vessels within the storm radius are identified
and delay and demurrage are estimated.

### Formula and assumptions

The Haversine calculation uses Earth radius 3,440.065 nautical miles.
Base delay is D = min(7, max(0, 0.25(W − 12))) × T, where W is wind
speed in m/s and T is the duration multiplier. Vessel-specific delay is
adjusted by distance from the storm centre; demurrage cost is vessel
delay × daily demurrage.

  Parameter            Default / range
  -------------------- --------------------------------
  Wind speed           25 m/s
  Storm radius         900 nautical miles
  Demurrage            \$900 per day
  Maximum base delay   7 days before duration scaling
  Duration             0.5× to 5×
  Cost variation       20% standard deviation
  Sampling             1,000 samples; seed 42

Outputs include vessels within radius, affected ports, delay per vessel,
total delay days, expected delay/demurrage cost, P10/P90 estimates,
cost-versus-wind and cost-versus-duration charts, and affected-vessel
table.

## 13. Customs Simulator

Function: run_customs(a). Purpose: evaluate customs inspections,
shipment holds, missing documents, clearance delays, storage costs, and
duty impact.

### Inputs and processing

Inputs include hold percentage, additional dwell days, storage cost per
day, duty change, inspection rate, missing-document percentage, and
missing-document delay. It retrieves shipments in In Transit, Port
Congestion Delay, Anchorage Pending, and Customs Hold statuses, plus
customs fees and prices from open quotes.

The simulator adjusts the hold rate using Hₐ = clip(H × (1 + 2I), 0, 1),
calculates held shipments, then selects missing-document shipments from
the remaining set to avoid double counting. It calculates dwell and
document delays, storage/holding costs, and duty impact. Direct
calculations use 1,000 samples and seed 42.

  Parameter                Default
  ------------------------ ------------------------
  Initial hold rate        20%
  Base dwell time          4 days
  Storage cost             \$180/day
  Inspection rate          5%
  Missing-document rate    0%
  Missing-document delay   2 days
  Cost variation           15% standard deviation

Outputs include held and missing-document shipment counts, adjusted hold
rate, holding cost per day, expected storage/delay cost, P10/P90
estimates, duty impact, most affected destination port, and
delayed-shipment table. The holding-cost schedule displays 1, 3, 5, 7,
and 14 days.

## 14. Milestone 3 --- Simulator Enhancement Summary

The Milestone 3 work enhanced the five existing simulators to address
fixed-input and single-result limitations. The improvements include
operational starting values retrieved from SQLite, editable scenario
assumptions, Monte Carlo sampling where implemented, percentile outputs,
fixed seeds for reproducibility, and additional KPIs, charts, and
tables.

  Area              Enhancement
  ----------------- ----------------------------------------------------
  Data              Operational starting values retrieved from SQLite.
  Inputs            Editable scenario assumptions in simulator forms.
  Uncertainty       Monte Carlo sampling in relevant calculations.
  Percentiles       P10, P50, and P90 where applicable.
  Reproducibility   Fixed random seeds.
  Visualization     KPI cards, charts, and data tables.
  Risk analysis     Shared distributions and sensitivity tools.

Individual freight simulator functions use NumPy seed 42. The shared
Monte Carlo module uses a separate generator with seed 11. A fixed seed
makes the sampling repeatable for the same inputs and data; it does not
guarantee accuracy.

## 15. Monte Carlo Simulation and Uncertainty Analysis

Monte Carlo simulation repeatedly evaluates a calculation using randomly
sampled inputs to estimate a distribution of possible outcomes rather
than one deterministic value. Direct uncertainty calculations in
individual freight simulators generally use 1,000 samples. The shared
module uses 1,500 iterations and seed 11.

### Percentiles

-   P10: value below which 10% of simulated outcomes fall.
-   P50: median simulated outcome.
-   P90: value below which 90% of simulated outcomes fall.
-   The P10--P90 interval contains the middle 80% of simulated outcomes;
    it is not the minimum-to-maximum range. An illustrative example in
    the source gives P10 = \$8,000, P50 = \$10,500, and P90 = \$14,000;
    this means the middle 80% of simulated results fall between \$8,000
    and \$14,000.

### Shared analysis and visualizations

-   Distribution chart: frequency or probability distribution of
    outcomes.
-   Exceedance curve: probability that an outcome exceeds a selected
    threshold.
-   Fan chart: spread over time, with P5--P95 and P25--P75 bands and
    median.
-   Tornado chart: one-at-a-time sensitivity of the result to input
    parameters.
-   Heat map: combined effect of two input parameters.
-   Risk metrics: mean, standard deviation, P5, P10, P50, P90, P95, VaR
    95, CVaR 95, and probability of being worse than baseline when
    supplied. The shared Monte Carlo layer is separate from direct
    percentile calculations in sim_fq.py. It should not be claimed that
    every shared chart is generated by every individual simulator.

## 16. Digital Twin and What-If Analysis

The Digital Twin evaluates hypothetical changes to the wider freight
system. Unlike an individual simulator, it can evaluate broader
operational changes by running existing agents and the decision engine
against a private database copy. Main implementations are twin.py and
twin2.py.

### Digital Twin v1 process

1.  Create a temporary SQLite database copy using online backup.
2.  Redirect the agent engine's thread-local database connection to the
    copy.
3.  Apply the hypothetical scenario mutation to the copy.
4.  Execute relevant agents and the Intelligence Engine.
5.  Compare baseline and modified scenario results.
6.  Restore the previous database connection, close the copy, and delete
    the temporary file.

### Digital Twin v2

-   Supports multiple simultaneous scenario shocks, financial impact
    calculations, uncertainty analysis, mitigation ranking, scenario
    saving, and baseline-versus-scenario comparison.
-   Can run agents against the modified private copy and propose
    selected mitigations through the approval workflow. Example: a port
    strike and carrier capacity loss can be applied together to a
    private copy; agents run against the modified environment and
    results are compared with baseline. A private snapshot is not
    continuous real-time synchronization; results depend on the database
    state when the snapshot is created.

  -----------------------------------------------------------------------
  Individual simulators               Digital Twin
  ----------------------------------- -----------------------------------
  Focus on a specific disruption.     Evaluates broader system-level
                                      scenarios.

  Use simulator-specific inputs and   Applies hypothetical changes to a
  calculations.                       private database copy.

  Produce disruption-specific cost or Re-runs agents and decision engine,
  delay estimates.                    then compares baseline and
                                      scenario.
  -----------------------------------------------------------------------

## 17. AI Copilot and SQL-Based Question Answering

The AI Copilot lets users ask natural-language questions about freight
operations. It supports intent recognition, typo correction, follow-ups,
entity comparison, daily briefings, SQL answers, RAG answers, source
information, feedback collection, and unanswered-question logging.
Qwen2.5-Instruct supports explanations and contextual responses.

### SQL question answering

The SQL engine answers structured questions from SQLite, such as
shipment counts, carrier comparisons, average quote value, quotes
awaiting approval, and ports with high congestion. It identifies
question intent and uses controlled, read-only, parameterized SQL logic.
Numerical answers are calculated from database records rather than
freely invented by a language model. Relevant modules include
analyst.py, qa.py, intent_router.py, and copilot_pro.py.

### SQL versus RAG

  -----------------------------------------------------------------------
  SQL                                 RAG
  ----------------------------------- -----------------------------------
  Uses structured database records.   Uses unstructured documents and
                                      text.

  Provides exact counts, totals,      Retrieves relevant passages for
  averages, and comparisons from      contextual answers.
  queries.                            

  Useful for current operational      Useful for policies, customs
  records.                            information, and guidelines.
  -----------------------------------------------------------------------

## 18. Retrieval-Augmented Generation (RAG)

RAG combines document retrieval with language-model answer generation.
Instead of relying only on model training, it retrieves relevant
passages from an external knowledge base and uses them as context.

### RAG workflow

1.  Collect documents and extract text.
2.  Divide text into overlapping chunks.
3.  Generate embeddings and store them in a vector index.
4.  Build a keyword-search index.
5.  Retrieve candidate passages using dense and keyword search.
6.  Combine rankings and rerank candidates.
7.  Pass selected context to the answer-generation layer.
8.  Generate an answer supported by retrieved information. The maritime
    knowledge base can contain Incoterms, HS code classification,
    customs requirements, shipping documentation, dangerous-goods
    regulations, demurrage, detention, cargo insurance, freight
    surcharges, and trade/shipping policies.

## 19. FreightQuote AI RAG Builder --- Collection and Processing

The separate notebook FreightQuoteAI_RAG_Builder_FINAL\_.ipynb builds
the maritime knowledge base. It has two stages: the original builder for
crawling, PDF discovery, extraction, chunking, and initial indexes; and
V2 for multilingual embeddings, improved BM25, hybrid retrieval,
reranking, evaluation, and export.

### Sources and crawling

Configured seed sources include IATA, World Customs Organization, US
Customs and Border Protection, World Bank, UNCTAD, UK customs guidance,
European Commission, Federal Maritime Commission, and maritime/trade
resources. The crawler uses Requests, BeautifulSoup, lxml, URL parsing,
and JSON manifests.

  Crawler setting                Value
  ------------------------------ ----------------
  Maximum crawl depth            2
  Maximum PDFs per seed          50
  Request timeout                15 seconds
  PDF download timeout           25 seconds
  Delay between requests         0.4 seconds
  Initial chunk size / overlap   400 / 50 words

PDF discovery is automatic only within the configured crawl scope; it
does not guarantee that every PDF or linked domain is discovered.
Downloaded source files are stored in Google Drive.

### Extraction, built-in knowledge, and chunking

PyMuPDF extracts PDF text and BeautifulSoup extracts readable HTML text.
Extracted records are saved in pdf_extracted.jsonl. Built-in freight
reference content includes Incoterms, HS codes, customs requirements,
cargo documentation, freight terminology, and maritime operations,
stored in freight_kb.jsonl. Processed chunks are stored in
all_chunks.jsonl with chunk ID, title, text, source, and word count.

The later indexing stage uses 350-word chunks with 70-word overlap. The
original builder also has its own initial extraction/chunk
configuration. Overlap helps preserve context across chunk boundaries.

## 20. Hybrid Retrieval, Vector Search, and Reranking

### Dense retrieval and FAISS

The original builder uses all-MiniLM-L6-v2 and an initial FAISS IVF Flat
index with inner-product similarity. The V2 pipeline uses
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, normalizes
embeddings, and uses FAISS for semantic retrieval. V2 exports the
multilingual model specification.

### BM25 keyword retrieval

BM25 provides lexical retrieval for exact terms such as FOB, CIF, HS
codes, customs document names, abbreviations, and maritime terminology.
The V2 implementation includes tokenization, stop-word removal, light
stemming, term frequency, document frequency, and inverse document
frequency. Parameters: k1 = 1.5 and b = 0.75.

### Hybrid fusion and reranking

V2 combines dense and BM25 rankings using Reciprocal Rank Fusion: RRF(d)
= Σᵢ 1/(60 + rankᵢ(d)). The constant 60 reduces the influence of small
rank differences. The cross-encoder cross-encoder/ms-marco-MiniLM-L-6-v2
evaluates the query and each candidate passage together, assigns
relevance scores, and reorders the candidates before answer generation.

## 21. Retrieval Evaluation, Knowledge Export, and Notebook Integration

### Evaluation

The V2 builder compares BM25-only, dense-only, hybrid RRF, and hybrid
plus cross-encoder reranking. It uses Recall@1, Recall@3, and Mean
Reciprocal Rank (MRR). Evaluation requires a labelled qa.csv with
question and title columns. Recall@1 checks whether the expected
document is first; Recall@3 checks whether it appears in the top three;
MRR averages the reciprocal rank of the correct document. These metrics
must only be reported as measured results if qa.csv is supplied and the
evaluation is executed.

### Export and import

The builder exports kb_export.json in kb-v1 format. The V2 export
includes embedding model name, document titles, source information,
chunk text, and Base64-encoded embeddings. The main application can
import it through AI Copilot → Knowledge Base → Import a Corpus. The
main application also supports configured Drive-backed
all_chunks.jsonl/index loading.

### Two-notebook integration

1.  Run the RAG Builder and mount Google Drive.
2.  Crawl, extract, chunk, and build FAISS/BM25 indexes.
3.  Run V2 multilingual embedding, hybrid retrieval, and reranking
    preparation.
4.  Run labelled retrieval evaluation if qa.csv is available.
5.  Export kb_export.json to persistent storage.
6.  Start the main application notebook and load/import the corpus.
7.  Ask Copilot questions to retrieve passages and generate contextual
    answers. Separate Colab runtimes do not share in-memory Python
    variables or temporary /content files. The notebooks communicate
    through persisted Google Drive resources or explicit corpus import.
    The selected integration method must point to the same generated
    corpus and index files.

## 22. Database Architecture

SQLite is the main operational database. It stores freight records,
agent results, users, approvals, Copilot conversations, knowledge-base
chunks, and model/scenario information. The database uses WAL mode and
supports online backups.

  -----------------------------------------------------------------------
  Data group                          Important tables
  ----------------------------------- -----------------------------------
  Freight                             quote_requests, freight_quotes,
                                      freight_rates, shipments,
                                      shipment_docs, vessels, ais_map,
                                      ports, carriers, customers,
                                      customs_rules, weather_risks,
                                      wx_live

  Agent and decision                  agent_runs, decisions, alerts,
                                      agent_actions, approval_steps,
                                      live_events, live_state

  Copilot and knowledge               copilot_chats, chat_history,
                                      copilot_log, copilot_feedback,
                                      copilot_unanswered, copilot_taught,
                                      kb_chunks

  Scenario and model                  ml_models, ml_metrics,
                                      twin_scenarios

  Audit and feeds                     audit_log, feed_urls, feed_log,
                                      feed_rejects, feed_idem, real_feed
  -----------------------------------------------------------------------

The RAG Builder also maintains separate index and export resources in
Google Drive; these are not the same as the operational SQLite database.

## 23. Authentication, Security, Background Processing, and Data Feeds

### Security mechanisms

-   PBKDF2-SHA256 password hashing with salt; JWT sessions using
    HTTP-only cookies.
-   Role-based access control and action-level permission checks.
-   Progressive login lockout and session revocation.
-   Content Security Policy, X-Frame-Options, request IDs, and per-IP
    rate limits.
-   PII masking, data export and erase-request functionality, and audit
    logging.
-   Four-eyes approval principle; critical actions can require an
    additional Admin approval.

  -----------------------------------------------------------------------
  Role                                Responsibility
  ----------------------------------- -----------------------------------
  Customer                            Requests freight quotations.

  Freight Broker                      Handles quotations and customs
                                      documentation.

  Operations Manager                  Reviews operational risks and
                                      approvals.

  Auditor                             Reviews records and audit
                                      information.

  Admin                               Manages system settings, users,
                                      policies, and administration.
  -----------------------------------------------------------------------

### Background processing and data feeds

A separate background worker supports periodic agent cycles, fleet
monitoring, weather updates, alert processing, data-feed ingestion,
validation, operational event processing, and scheduled reports. Feed
modules can import CSV files and configured URLs; invalid records can be
rejected or quarantined. Open-Meteo provides real weather and marine
information. Vessel positions, shipment records, carrier information,
and pricing training data in the demonstration environment may be
simulated. Real-time AIS and external freight-rate integration require
suitable providers.

## 24. Frontend, API Architecture, and Project Structure

The application uses a server-driven single-page interface: the backend
sends structured UI blocks and the frontend renders them. The interface
includes KPI cards, tables, charts, forms, maps, alerts, approval
actions, and Copilot conversations. Vanilla JavaScript, custom CSS,
Apache ECharts, Leaflet, and Server-Sent Events support visualizations,
maps, streaming responses, and live updates.

  -----------------------------------------------------------------------
  API group                           Purpose
  ----------------------------------- -----------------------------------
  Copilot                             Ask, stream, teach, and test
                                      Copilot.

  Freight                             Quote creation, documents,
                                      rerouting, and storm-related
                                      operations.

  Pages and Data                      Dashboard views, detail pages,
                                      exports, and reports.

  Agents                              Run agents, execute cycles, and
                                      access simulations.

  Digital Twin                        Run and compare what-if scenarios.

  Knowledge Base                      Upload, search, import, export, and
                                      evaluate knowledge.

  Accounts                            Login, OTP, and user management.

  Operations                          Health checks, streams, feeds, and
                                      translation.
  -----------------------------------------------------------------------

### Important generated modules

  -----------------------------------------------------------------------
  Module                              Responsibility
  ----------------------------------- -----------------------------------
  server.py                           FastAPI application and API
                                      routing.

  domain_freight.py                   Freight agents, quote workflow, and
                                      fleet watchers.

  live_engine.py / live_rbac.py       Agent runtime, decisions,
                                      approvals, and permissions.

  sim_fq.py / twin.py / twin2.py      Five simulators and Digital Twin
                                      versions.

  mc_sims.py / mc.py                  Monte Carlo calculations and
                                      visualizations.

  seanav.py / weather.py              Maritime routing and weather
                                      integration.

  rag.py / kb_pack.py                 Main-app retrieval and
                                      knowledge-base packaging.

  copilot_pro.py / analyst.py / qa.py Copilot, structured analysis, and
  / intent_router.py                  SQL question answering.

  db.py / authx.py / hardening.py /   Database, authentication, security,
  privacy.py                          and privacy.

  data_feeder.py / validate.py /      Data feeds, validation, background
  worker.py / persist.py              tasks, and backups.

  views_core.py / views_freight.py /  UI page generation and reusable
  views_misc.py / blocks.py           components.

  reports.py / gpu.py / llm_engine.py Reports, model loading, language
  / lang_pack.py / mailer.py          support, and email.
  -----------------------------------------------------------------------

The generated project also includes static/index.html, static/app.js,
and static/style.css. The RAG Builder stores source PDFs, JSONL corpora,
FAISS indexes, BM25 indexes, model resources, and kb_export.json in
Google Drive. These resources are separate from the main SQLite
database.

## 25. Deployment, End-to-End Scenarios, Testing, Limitations, Future Work, and Conclusion

### Deployment

1.  Open the main FreightQuote AI notebook in Google Colab and select a
    compatible GPU runtime, such as NVIDIA T4.
2.  Run notebook cells in order and install required libraries.
3.  Mount Google Drive if persistence or an external knowledge base is
    required; restore or initialize SQLite.
4.  Generate application modules and frontend resources; load configured
    ML and language models.
5.  Start FastAPI with Uvicorn on port 8000 and access through the Colab
    port proxy or configured ngrok fallback.
6.  Configure external credentials through Colab Secrets or environment
    settings; do not hard-code credentials or commit them to source
    control. The RAG Builder is deployed separately: mount Drive,
    install crawling/PDF/embedding dependencies, run crawling and
    extraction, build chunks and indexes, prepare V2 retrieval,
    optionally evaluate with qa.csv, export kb_export.json, and import
    it into the main application. Some features, including email
    notifications, external model access, and ngrok fallback, require
    corresponding credentials/configuration.

### Illustrative end-to-end scenarios

  -----------------------------------------------------------------------
  Scenario                            Flow
  ----------------------------------- -----------------------------------
  Freight quote with weather          Request saved → route and weather
  disruption                          evaluated → high risk triggers
                                      replanning → price and customs
                                      checked → margin evaluated →
                                      decision/approval.

  Carrier capacity loss               Select carrier and capacity loss →
                                      identify affected shipments → rank
                                      alternatives → check capacity →
                                      reassign or mark NO CAPACITY →
                                      estimate cost/delay.

  Customs delay                       Set hold/inspection assumptions →
                                      identify held and missing-document
                                      shipments separately → estimate
                                      delay, storage, and duty impact →
                                      display percentiles.

  Digital Twin what-if                Create private copy → apply
                                      hypothetical change → run agents
                                      and decision engine → compare with
                                      baseline → rank/propose mitigation.

  Copilot knowledge retrieval         Ask a maritime question → retrieve
                                      with BM25 and dense search →
                                      combine rankings → rerank →
                                      generate answer from retrieved
                                      context.
  -----------------------------------------------------------------------

### Testing and validation

-   Agent testing: execution, result generation, conditional replanning,
    decisions, and approvals.
-   Simulator testing: database retrieval, scenario inputs,
    baseline/modified calculations, percentiles, reproducibility,
    empty-data handling, and outputs.
-   Digital Twin testing: private-copy creation, mutation, agent
    execution, baseline comparison, connection restoration, and
    temporary-file cleanup.
-   RAG testing: crawling, PDF discovery, extraction, chunking, indexes,
    hybrid retrieval, reranking, labelled evaluation, export, and
    import.
-   Database integrity: verify relevant records and values, not only
    table counts, when checking that live data remains unchanged.
    Successful execution of a simulator or test cell demonstrates that
    the workflow ran; it does not independently establish real-world
    accuracy of its financial assumptions or predictive models.

### Assumptions and limitations

-   Demonstration vessel, shipment, carrier, and pricing-training data
    may be simulated; verified real-time AIS and commercial freight
    rates require external providers.
-   Weather freshness depends on Open-Meteo availability and network
    connectivity.
-   Simulator assumptions for vessel speed, freight rates, delay costs,
    capacity, storm duration, demurrage, inspection, and
    missing-document delays require calibration against real operational
    history.
-   Monte Carlo results depend on the chosen distributions, assumptions,
    and input data. A fixed seed provides repeatability, not accuracy.
-   Digital Twin scenarios use a database snapshot and are not
    automatically continuously synchronized with live data.
-   RAG crawling is limited to configured seed sites and crawl limits;
    coverage is not guaranteed to be exhaustive.
-   Recall@1, Recall@3, and MRR require a labelled qa.csv and executed
    evaluation; do not report unmeasured values.
-   External email, Slack, and SMS notifications require credentials and
    configuration.

### Future enhancements

-   Integrate verified real-time AIS vessel tracking and commercial
    freight-rate/carrier APIs.
-   Calibrate pricing and congestion models using historical operational
    records.
-   Validate simulation distributions and percentile estimates against
    observed outcomes.
-   Extend multi-disruption optimization and, if required, continuous
    Digital Twin synchronization.
-   Expand labelled RAG evaluation datasets and maritime
    regulatory/document sources.
-   Improve automated tests, production deployment infrastructure,
    monitoring, and operational risk analytics.

### Conclusion

FreightQuote AI integrates agent-based automation, machine learning,
maritime route optimization, five freight simulators, Monte Carlo
analysis, a Digital Twin, and Retrieval-Augmented Generation into a
unified maritime freight management platform. Specialized agents
evaluate route, weather, pricing, customs, margin, documentation, and
alerts. The simulators estimate the impact of individual disruptions,
while the Digital Twin tests broader hypothetical changes against a
private database copy. The separate RAG Builder prepares a searchable
maritime knowledge base, and the AI Copilot connects structured database
answers with document-based retrieval. Together, these components
support more informed, transparent, and data-driven maritime freight
pricing and operational decisions.

## Contents --- 25 Main Topics

1.  Project Overview, Problem Statement and Objectives
2.  Key Features and Overall System Architecture
3.  Technology Stack
4.  Application Workflow and Decision Process
5.  Multi-Agent Architecture and Agent Responsibilities
6.  Fleet Monitoring System
7.  Machine Learning Models and Algorithms
8.  Five Enhanced Freight Simulators --- Common Design
9.  Route Simulator
10. Quote Simulator
11. Carrier Simulator
12. Weather Simulator
13. Customs Simulator
14. Milestone 3 --- Simulator Enhancement Summary
15. Monte Carlo Simulation and Uncertainty Analysis
16. Digital Twin and What-If Analysis
17. AI Copilot and SQL-Based Question Answering
18. Retrieval-Augmented Generation (RAG)
19. FreightQuote AI RAG Builder --- Collection and Processing
20. Hybrid Retrieval, Vector Search, and Reranking
21. Retrieval Evaluation, Knowledge Export, and Notebook Integration
22. Database Architecture
23. Authentication, Security, Background Processing, and Data Feeds
24. Frontend, API Architecture, and Project Structure
25. Deployment, End-to-End Scenarios, Testing, Limitations, Future Work,
    and Conclusion

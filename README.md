GreenTwin: Sustainable Logistics Digital Twin Prototype
🚀 Overview
GreenTwin is an innovative AI-driven digital twin and route optimization system meticulously designed to address the complexities of sustainable logistics. This prototype demonstrates a sophisticated approach to supply chain management by integrating real-time environmental factors with advanced simulation capabilities. Our core goal is to enable businesses to optimize their delivery operations not just for efficiency, but also for minimal carbon footprint across diverse global locations.

✨ Key Features & Innovations
Global & Country-Specific Network Modeling:

Handles supply chain nodes (Distribution Centers and Stores) across multiple countries (India, USA, UK, Australia).

Features a country selection dropdown to dynamically load and visualize the network for a specific region.

Map view automatically centers and zooms to the selected country for a more realistic and focused animation.

Advanced Route Optimization:

Employs a sophisticated Traveling Salesperson Problem (TSP) solver (conceptually using techniques similar to Google OR-Tools for optimal pathfinding) to generate highly efficient routes.

Moves beyond naive greedy approaches to provide more realistic and optimized paths.

Dynamic Delivery Simulation (Digital Twin):

Models multi-truck operations (heterogeneous EV and Diesel fleets) with capacity and demand constraints.

Incorporates real-time environmental and operational factors (mocked traffic congestion, weather conditions, and crucial electricity grid carbon intensity) which dynamically affect travel times.

EV Speed Adjustment: EVs are realistically penalized (slow down) when operating in areas with high grid carbon intensity, reflecting the conceptual cost of using "dirty" electricity.

Quantifiable Carbon Footprint:

Explicitly calculates and visualizes CO2 emissions per trip and cumulatively, allowing for direct comparison and optimization based on the "greenness" of the electricity grid (for EVs) and fuel type.

This moves beyond abstract "green" concepts to measurable environmental impact.

Conceptual Dynamic Re-routing & Trade-off Analysis:

Visualizes hypothetical re-route opportunities triggered during simulation (e.g., due to high carbon intensity for an EV).

Presents a dynamically changing table below the simulation map that details the trade-offs for each re-route event:

Why the re-route was considered (e.g., "High Carbon Grid Intensity").

Quantifiable emission reduction vs. cost increase/decrease and time change for the alternative path.

Includes a dropdown to select a specific truck to observe its re-route details closely.

A "Final Simulation Summary" provides an overview of all re-route events or the planned routes if none occurred.

Interactive Multi-Page Dashboard (Black & Red Theme):

Built with Streamlit, providing an intuitive, black-and-red themed interface with distinct sections for:

Overview: High-level summary insights and key performance indicators (KPIs) including total emissions.

Network & Optimization: Visualization of the global supply chain network and the computed optimal route.

Simulation & Animation: Interactive slider to "play back" truck movements on a live map with a clear legend for colors, showcasing dynamic impacts and re-route alternatives.

Scenario Comparison: A dedicated page to compare multiple simulation runs (e.g., "All EV Fleet" vs. "Mixed Fleet") side-by-side based on their total emissions and time, supported by interactive bar charts.

Configuration: Adjust truck fleet parameters (type, speed, capacity, emission rates, EV consumption).

Raw Logs: Detailed segment-by-segment simulation data with export capabilities.

Scalable Architecture: Designed with modular components, facilitating future integration with live API feeds (e.g., Google Maps Directions, OpenWeatherMap, ElectricityMap), more complex VRP solvers, and predictive analytics.

💡 The Innovation - Why GreenTwin Stands Out
Traditional logistics planning often relies on static data, ignoring dynamic real-world conditions and the true environmental cost. GreenTwin's innovation lies in its ability to simulate dynamic, real-world scenarios to inform sustainable decision-making:

Quantifiable Carbon-Aware Logistics: It moves from a vague notion of "green" to a concrete, measurable impact. By dynamically considering grid carbon intensity for EVs, it quantifies the true environmental cost and highlights opportunities for greener operations.

Proactive Decision Support Foundation: While the prototype uses conceptual re-routes, it vividly demonstrates the potential for real-time, predictive optimization – anticipating issues like high carbon periods or congestion to proactively adjust routes.

Comprehensive Trade-off Analysis: The ability to compare scenarios and analyze re-route trade-offs (emissions vs. cost vs. time) directly supports complex operational decisions for a greener, more efficient supply chain.

🛠️ Setup & Installation
This project is built using Python and Streamlit.

Clone the repository:

git clone https://github.com/your-username/green-twin.git
cd green-twin

Create and activate a Python virtual environment (highly recommended):

python3 -m venv venv
source venv/bin/activate
# On Windows, use: venv\Scripts\activate

Install the required dependencies:

pip install -r requirements.txt

(Ensure your requirements.txt contains: streamlit, pandas, numpy, networkx, pydeck, plotly)

Data Files:
Ensure network.csv and demand.csv are present in the data/ directory. Expanded example data files for multiple countries are provided within the repository.

Configure Dark Theme (Essential for Visuals):
Create a hidden directory .streamlit in your project's root folder (if it doesn't exist):

mkdir .streamlit

Then, create a file named config.toml inside the .streamlit folder:

touch .streamlit/config.toml

Open config.toml with a text editor and paste the following content:

[theme]
primaryColor="#EF4444" # A bright red for primary elements
backgroundColor="#0A0A0A" # Deep black background
secondaryBackgroundColor="#1A1A1A" # Slightly lighter black for sidebars/panels
textColor="#FAFAFA" # Off-white for general text
font="sans serif"

[global]
disableWatchdogWarning = true

Save and close the file.

🚀 Running the Application
Once setup is complete, run the Streamlit application from your terminal:

streamlit run app.py

This will open the GreenTwin dashboard in your web browser (usually at http://localhost:8501). If it doesn't open automatically, copy the "Local URL" from your terminal and paste it into your browser.

📊 Dashboard Usage
Select Country: Use the "Select Country" dropdown in the sidebar to focus the simulation on India, USA, UK, or Australia.

Compute Optimal Route: Navigate to "🌐 Network & Optimization" and click "Compute Optimal Route".

Run Simulation: Go to "🚚 Simulation & Animation" and click "Run Simulation".

Use the "Simulation Time (hours)" slider to animate truck movements.

Observe the "Current Simulation Factors" for active trucks.

Look for "Dynamic Re-route Opportunities" below the map. Select a truck to see detailed trade-offs if a re-route event was triggered.

Scroll down to "🏁 Final Simulation Summary" for an overview of re-routes or final planned paths.

Configure Fleet: Visit "⚙️ Configuration" to add/remove trucks, change types (EV/Diesel), and adjust their parameters (speed, capacity, emission rates, EV consumption).

Compare Scenarios: After running multiple simulations with different configurations, go to "⚖️ Scenario Comparison" to see a side-by-side quantitative and visual comparison of their total emissions and time.

Raw Data: "📜 Raw Logs" allows you to inspect and download the detailed simulation data.

🛣️ Future Enhancements
Full OR-Tools VRP Integration: Transition from conceptual TSP to a robust Vehicle Routing Problem solver in a dedicated backend service for multi-vehicle, multi-depot, time-windowed optimization.

Live API Integration: Connect to actual Google Maps Platform APIs (Directions, Traffic, Weather) and real-time electricity grid carbon intensity APIs (e.g., ElectricityMap, WattTime) for live data feeds.

Predictive Analytics: Incorporate machine learning models to forecast traffic, weather, and carbon intensity to enable proactive route and schedule optimization.

Cost/Profitability Analysis: Add financial metrics alongside environmental ones.

User Authentication & Data Persistence: Implement user logins and save/load scenarios using a database.

Developed for a National Level Hackathon by [Your Name/Team Name]

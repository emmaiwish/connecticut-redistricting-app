# Connecticut Apportionment & Redistricting Application

An interactive web application for exploring Connecticut municipal redistricting, demographic characteristics, voter registration, and population patterns.

## Developed by Emma Wishneski
**University of Connecticut, Class of 2026**

## About the Project

The Connecticut Apportionment & Redistricting Application is an interactive mapping and analysis tool designed to support the exploration of municipal redistricting in Connecticut.

The application allows users to create hypothetical districts by assigning Connecticut towns to one of five districts directly through an interactive map. As towns are assigned, the application dynamically summarizes district characteristics and calculates geographic compactness, allowing users to examine how different district configurations affect the geographic and demographic composition of each district.

Additional maps provide statewide context through visualizations of voter registration and population across Connecticut municipalities.

This project was developed as a Capstone project for the University of Connecticut's Applied Data Analysis program. 

## Live Application

The application is publicly available through Posit Connect Cloud:

**[Open the Connecticut Apportionment & Redistricting Application](https://jeffreyladewig-connecticut-redistricting-app.share.connect.posit.cloud/)**

No installation or account is required to use the public application.

## Features

### Interactive Redistricting Tool

Users can:

- Assign Connecticut towns to one of five districts by clicking directly on the map
- Move towns between districts or remove existing assignments
- Reset an individual district or reset the entire map
- View the number of municipalities assigned to each district
- View aggregated demographic information for each district
- Monitor unassigned towns and geographic areas
- Export district assignments and summary statistics as a CSV file

### District Compactness

The application calculates a **Polsby-Popper compactness score** for each proposed district.

The Polsby-Popper measure is calculated as:

`4π × Area / Perimeter²`

Scores range from 0 to 1, with higher values representing more geographically compact district shapes. Municipalities assigned to the same district are combined before area and perimeter are calculated.

Compactness scores update as users modify their proposed districts.

### Voter Registration Map

A separate statewide map visualizes **2020 Democratic and Republican voter registration** by municipality.

The visualization displays the relative Democratic or Republican registration advantage for each municipality, with interactive tooltips providing additional registration information.

### Population Map

The application also includes an interactive map of **2020 municipal population** across Connecticut.

Municipalities are shaded according to population, allowing users to compare population patterns geographically across the state.

## Data

The application combines Connecticut municipal geographic boundaries with town-level demographic, population, and voter registration data.

Municipal boundaries are based on **2025 U.S. Census Bureau TIGER/Line county subdivision geographic data for Connecticut**.

Town-level demographic, population, and voter registration data used by the application were provided by Professor Jeffery Ladewig of the University of Connecticut.

## Technology

The application was developed using:

- **Python**
- **Shiny for Python** for the interactive web application
- **GeoPandas** for geographic data processing and spatial calculations
- **pandas** for data manipulation and aggregation
- **Leaflet** for interactive web mapping
- **OpenStreetMap** for map tiles
- **GitHub** for version control and application maintenance
- **Posit Connect Cloud** for public deployment and hosting

## Repository Structure

    connecticut-redistricting-app/
    ├── app.py
    ├── requirements.txt
    ├── data/
    └── README.md

- `app.py` contains the application's user interface, server logic, mapping functionality, and analytical calculations.
- `data/` contains the geographic and town-level datasets used by the application.
- `requirements.txt` identifies the Python packages required to run and deploy the application.

## Updating the Application

The public application is deployed to Posit Connect Cloud from the `Main` branch of this repository.

Changes pushed to the `Main` branch automatically trigger a new deployment through Posit Connect Cloud. This allows the application's code and underlying datasets to be updated as new data become available.

## Development

**Application development and implementation:** Emma Wishneski  
**Faculty collaborator:** Professor Jeffery Ladewig, Political Science Department, University of Connecticut

This application was developed as a tool for exploring Connecticut municipal redistricting and the geographic and demographic characteristics associated with potential district configurations.
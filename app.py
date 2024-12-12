import gradio as gr
import pandas as pd
import matplotlib.pyplot as plt
import io
import openai
import os
import tempfile
import numpy as np

# Configuration de l'API OpenAI
client = openai.OpenAI(api_key='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')

# Fonction pour analyser le tableau avec GPT
def analyze_table(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        analysis_text = response.choices[0].message.content.strip()
    except Exception as e:
        analysis_text = f"Une erreur s'est produite lors de l'analyse du tableau: {e}"
    return analysis_text

# Fonction pour charger les fichiers Excel et effectuer les calculs
def upload_and_process_files(vehicle_data_file, charging_station_file, electric_vehicle_file):
    try:

        # Charger les fichiers Excel dans des DataFrames Pandas
        vehicle_data = pd.read_excel(vehicle_data_file)
        charging_station_data = pd.read_excel(charging_station_file)
        electric_vehicle_data = pd.read_excel(electric_vehicle_file)
        
        # Calculer l'année de conversion
        total_vehicles = len(vehicle_data)
        group_size = total_vehicles // 10
        current_group = 1
        count = 0

        for index, row in vehicle_data.iterrows():
            # Assigner l'année de conversion
            vehicle_data.at[index, 'annee_conversion'] = current_group

            count += 1
            if count >= group_size and current_group < 10:
                count = 0
                current_group += 1

        for index, vehicle in vehicle_data.iterrows():
            # Filtrer les véhicules électriques par catégorie correspondant à celle du véhicule thermique
            electric_vehicles = electric_vehicle_data[electric_vehicle_data['categorie_electrique'] == vehicle['categorie_thermique']]
            found_valid_ev = False
            conso_gaz_annee = vehicle['conso_L_h'] * vehicle['nbre_h_annuel']
            vehicle_data.at[index, 'reduction_GES'] = round((conso_gaz_annee * vehicle['val_carburant']) / 1000, 2)
            cout_litre = conso_gaz_annee * vehicle['prix_gaz']

            for _, ev in electric_vehicles.iterrows():
                capacite_batterie_90 = round(ev['capacite_batterie'] * 0.9, 2)
                conso_kwh_jrs_hiver = ev['conso_kWh_h_hiver'] * vehicle['nbre_h']
                conso_kwh_jrs_ete = round(ev['Conso_kWh_h_ete'] * vehicle['nbre_h'], 2)
                cout_kwh = (conso_kwh_jrs_hiver * (vehicle['nbre_jrs'] * 0.5) + conso_kwh_jrs_ete * (vehicle['nbre_jrs'] * 0.5)) * 0.11
                entretien_elec = vehicle['cout_entre_annuel'] * 0.5
                economy = round((cout_litre + vehicle['cout_entre_annuel']) - (cout_kwh + entretien_elec))
                pourc_am = (vehicle['fin_trajet_matin'] - vehicle['trajet_matin']) / \
                        ((vehicle['fin_trajet_matin'] - vehicle['trajet_matin']) + (vehicle['fin_trajet_aprs_midi'] - vehicle['trajet_aprs_midi']))
                pourc_pm = 1 - pourc_am
                residuel_90_am = capacite_batterie_90 - (conso_kwh_jrs_hiver * pourc_am)

                # Filtrer les bornes de recharge par catégorie correspondant à celle du véhicule
                charging_stations = charging_station_data[charging_station_data['categorie'] == vehicle['categorie_thermique']].sort_values('puiss_borne_recharg')

                for _, station in charging_stations.iterrows():
                    recharge_midi_kwh = station['puiss_borne_recharg'] * 0.9 * vehicle['recharge_midi_hre']
                    if recharge_midi_kwh > capacite_batterie_90:
                        recharge_midi_kwh = capacite_batterie_90
                    residuel_90_pm = round(capacite_batterie_90 if (recharge_midi_kwh + residuel_90_am) > capacite_batterie_90 \
                                    else (recharge_midi_kwh + residuel_90_am) - (conso_kwh_jrs_hiver * pourc_pm), 2)
                    
                    if residuel_90_pm > 0:
                        found_valid_ev = True
                        # Mettre à jour les données du véhicule avec les valeurs calculées
                        vehicle_data.at[index, 'modeleVE'] = ev['modeleVE']
                        vehicle_data.at[index, 'capacite_batterie'] = ev['capacite_batterie']
                        vehicle_data.at[index, 'Autonomie_h_hiver'] = round(ev['Autonomie_h_hiver'])
                        vehicle_data.at[index, 'Autonomie_h_ete'] = round(ev['Autonomie_h_ete'])
                        vehicle_data.at[index, 'cout_vehicl_elect'] = ev['cout_vehicl_elect']
                        vehicle_data.at[index, 'capacite_batterie_90'] = round(capacite_batterie_90, 2)
                        vehicle_data.at[index, 'conso_kwh_jrs_hiver'] = round(conso_kwh_jrs_hiver, 2)
                        vehicle_data.at[index, 'conso_kwh_jrs_ete'] = round(conso_kwh_jrs_ete, 2)
                        vehicle_data.at[index, 'residuel_90_am'] = round(residuel_90_am, 2)
                        vehicle_data.at[index, 'recharge_midi_kwh'] = round(recharge_midi_kwh, 2)
                        vehicle_data.at[index, 'residuel_90_pm'] = residuel_90_pm
                        vehicle_data.at[index, 'pourc_am'] = pourc_am
                        vehicle_data.at[index, 'pourc_pm'] = pourc_pm
                        vehicle_data.at[index, 'puiss_borne_recharg'] = station['puiss_borne_recharg']
                        vehicle_data.at[index, 'economy'] = economy
                        vehicle_data.at[index, 'recharge_soir_h'] = round((capacite_batterie_90 - residuel_90_pm) / station['puiss_borne_recharg'], 2)
                        break  # Break the loop if the calculations are successful for this EV model

            if not found_valid_ev:
                # Si aucun véhicule électrique valide n'a été trouvé
                vehicle_data.at[index, 'modeleVE'] = "Non electrifiable"
                vehicle_data.at[index, 'capacite_batterie'] = 0
                vehicle_data.at[index, 'capacite_batterie_90'] = 0
                vehicle_data.at[index, 'conso_kwh_jrs_hiver'] = 0
                vehicle_data.at[index, 'residuel_90_am'] = 0
            
        
        # Renommer les colonnes pour le premier tableau
        columns_table1 = {
            'numvehicle': 'Numéro du véhicule',
            'model': 'Modèle',
            'annee': 'Annee du Vehicule',
            'carburant': 'Carburant',
            'nbre_h': 'Distance en heure',
            'trajet_matin': 'Debut trajet AM',
            'fin_trajet_aprs_midi': 'Fin trajet PM'
        }
        table1 = vehicle_data[list(columns_table1.keys())].rename(columns=columns_table1)

        # Renommer les colonnes pour le deuxième tableau
        columns_table2 = {
            'numvehicle': 'Numero',
            'model': 'Marque Modele',
            'modeleVE': 'Equipement electrique Eq',
            'conso_kwh_jrs_hiver': 'Conso en kWh hiver',
            'Autonomie_h_hiver': 'Autonomie(h) hiver',
            'Autonomie_h_ete': 'Autonomie(Km) ete'
            
        }
        table2 = vehicle_data[list(columns_table2.keys())].rename(columns=columns_table2)

        # Renommer les colonnes pour le deuxième tableau
        columns_table3 = {
            'numvehicle': 'Numero',
            'model': 'Marque Modele',
            'modeleVE': 'Equipement electrique Eq',
            'annee': 'Annee',
            'nbre_h_annuel': 'Nbre heure annuel',
            'annee_conversion': 'Annee de conversion',
            'puiss_borne_recharg': 'Puissance de la borne'
            
        }
        table3 = vehicle_data[list(columns_table3.keys())].rename(columns=columns_table3)

        columns_table4 = {
            'numvehicle': 'Numero',
            'model': 'Marque Modele',
            'modeleVE': 'Equipement electrique Eq',
            'reduction_GES': 'Reduction de GES(CO2 teq'  
            
        }
        table4 = vehicle_data[list(columns_table4.keys())].rename(columns=columns_table4)

        columns_table5 = {
    'numvehicle': 'Numero',
    'model': 'Marque Modele',
    'annee': 'Annee du Vehicule',
    'modeleVE': 'Vehicule electrique Eq',
    'nbre_h': 'Distance Moyen',
    'annee_conversion': 'Annee de Conversion',
    'puiss_borne_recharg': 'Puissance Borne',
    'residuel_90_am': 'Residuel AM (kWh) 90%',
    'recharge_midi_kwh': 'Recharge Midi (kWh)',
    'residuel_90_pm': 'Residuel PM (kWh)',
    'recharge_soir_h': 'Recharge Batterie (h)'
}
        
        table5 = vehicle_data[list(columns_table5.keys())].rename(columns=columns_table5)

        columns_table6 = {
    'numvehicle': 'Numero',
    'model': 'Marque Modele',
    'nbre_h': 'Distance en heure',
    'modeleVE': 'Vehicule electrique Eq',
    'trajet_matin': 'Debut Trajet AM',
    'fin_trajet_matin': 'Fin Trajet AM',
    'trajet_aprs_midi': 'Debut Trajet PM',
    'fin_trajet_aprs_midi': 'Fin Trajet PM',
    'batiment': 'Batiment Attitre',
    'conso_kwh_jrs_ete': 'Conso (kWh/jour) ete',
    'conso_kwh_jrs_hiver': 'Conso (kWh/jour) hiver',
    'annee_conversion': 'Annee de Conversion',
    'recharge_midi_hre': 'Temps de Recharge Midi',
    'puiss_borne_recharg': 'Puissance Borne',
    'residuel_90_pm': 'Residuel PM (kWh)',
    'recharge_soir_h': 'Temps de recharge soir (h)'
}
        
        table6 = vehicle_data[list(columns_table6.keys())].rename(columns=columns_table6)


        message = "Importation et traitement réussis !"
    except Exception as e:
        vehicle_data = None
        charging_station_data = None
        electric_vehicle_data = None
        table1 = pd.DataFrame()
        table2 = pd.DataFrame()
        table3 = pd.DataFrame()
        table4 = pd.DataFrame()
        table5 = pd.DataFrame()
        table6 = pd.DataFrame()
        message = f"Erreur lors du traitement : {str(e)}"
    
    return vehicle_data, charging_station_data, electric_vehicle_data, table1, table2, table3, table4, table5, table6,  message

# Fonction pour télécharger les tableaux au format CSV
def download_table_as_csv(table):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
        table.to_csv(tmp_file.name, index=False)
        return tmp_file.name

# Fonction pour générer un graphique basé sur les données traitées
def generate_plot(vehicle_data):
    if vehicle_data is None:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'Aucune donnée disponible', fontsize=18, ha='center')
        ax.set_axis_off()
        return fig

    fig, ax1 = plt.subplots()

    ax1.plot(vehicle_data['numvehicle'], vehicle_data['conso_kwh_jrs_hiver'], color='skyblue')
    ax1.set_ylabel('Consommation hiver (kWh)', color='skyblue')

    ax2 = ax1.twinx()
    ax2.plot(vehicle_data['numvehicle'], vehicle_data['capacite_batterie_90'], color='red')
    ax2.set_ylabel('Capacité de la batterie (kWh)', color='red')

    plt.title('Consommation vs Capacité de la Batterie')
    return fig


def plot_png1(vehicle_data):
    if vehicle_data is None:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'Aucune donnée disponible', fontsize=18, ha='center')
        ax.set_axis_off()
        return fig
    vehicle_data = vehicle_data[vehicle_data['modeleVE']!='Non electrifiable']
    bar_width = 0.35
    r1 = np.arange(len(vehicle_data['numvehicle']))
    r2 = [x + bar_width for x in r1]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(r1, vehicle_data['nbre_h'], color='red', width=bar_width, edgecolor='grey', label='Heure de fonctionnement')
    ax.bar(r2, vehicle_data['Autonomie_h_hiver'], color='purple', width=bar_width, edgecolor='grey', label='Autonomie en heure hiver (Heure)')

    ax.set_xlabel('Numéro véhicule')
    ax.set_ylabel('Autonomie et heure de fonctionnement')
    ax.set_title('Autonomie et heure de fonctionnement')
    ax.set_xticks([r + bar_width/2 for r in range(len(vehicle_data['numvehicle']))])
    ax.set_xticklabels(vehicle_data['numvehicle'], rotation=45, ha="right")
    ax.legend()
    
    return fig





def plot_png(vehicle_data):
    if vehicle_data is None:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'Aucune donnée disponible', fontsize=18, ha='center')
        ax.set_axis_off()
        return fig
    vehicle_data = vehicle_data[vehicle_data['modeleVE']!='Non electrifiable']
    bar_width = 0.35
    r1 = np.arange(len(vehicle_data['numvehicle']))
    r2 = [x + bar_width for x in r1]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(r1, vehicle_data['conso_kwh_jrs_hiver'], color='blue', width=bar_width, edgecolor='grey', label='Consommation en kWh par jours en hiver')
    ax.bar(r2, vehicle_data['capacite_batterie_90'], color='yellow', width=bar_width, edgecolor='grey', label='Capacite de la batterie')

    ax.set_xlabel('Numéro véhicule')
    ax.set_ylabel('Consommation et capacite')
    ax.set_title('Consommation et capacite de batterie')
    ax.set_xticks([r + bar_width/2 for r in range(len(vehicle_data['numvehicle']))])
    ax.set_xticklabels(vehicle_data['numvehicle'], rotation=45, ha="right")
    ax.legend()
    
    return fig


def plot_png2(vehicle_data):
    if vehicle_data is None:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'Aucune donnée disponible', fontsize=18, ha='center')
        ax.set_axis_off()
        return fig
    vehicle_data = vehicle_data[vehicle_data['modeleVE']!='Non electrifiable']
    vehicle_data.loc[:, 'heure_dispo'] = 24 - vehicle_data['fin_trajet_aprs_midi'] + vehicle_data['trajet_matin']
    bar_width = 0.35
    r1 = np.arange(len(vehicle_data['numvehicle']))
    r2 = [x + bar_width for x in r1]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(r1, vehicle_data['heure_dispo'], color='limegreen', width=bar_width, edgecolor='grey', label='Temps de recharge possible soir (heure)')
    ax.bar(r2, vehicle_data['recharge_soir_h'], color='deepskyblue', width=bar_width, edgecolor='grey', label='Temps de recharge nécessaire Soir hiver (Heure)')

    ax.set_xlabel('Numéro véhicule')
    ax.set_ylabel('Temps de recharge (heures)')
    ax.set_title('Temps de recharge')
    ax.set_xticks([r + bar_width/2 for r in range(len(vehicle_data['numvehicle']))])
    ax.set_xticklabels(vehicle_data['numvehicle'], rotation=45, ha="right")
    ax.legend()
    
    return fig

# Fonction pour télécharger les tableaux au format CSV
def download_table_as_csv(table):
    # Créer un fichier temporaire pour le CSV
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    table.to_csv(temp_file.name, index=False)
    return temp_file.name  # Retourner le chemin du fichier CSV temporaire

# Interface Gradio
def gradio_app():
        

    with gr.Blocks(theme=gr.themes.Soft()) as demo:

        with gr.TabItem("Accueil"):  # Premier onglet pour la page d'accueil
            gr.HTML("""
            <div style="width: 100vw; height: 100vh; overflow: hidden; display: flex; align-items: center; justify-content: center;">
                <iframe src="https://player.vimeo.com/video/702467551?h=4c23bcd2ea&amp;autoplay=1&amp;loop=1&amp;background=1" 
                        frameborder="0" 
                        allow="autoplay; fullscreen" 
                        allowfullscreen 
                        style="width: 100%; height: 100%; border: none;">
                </iframe>
            </div>
            <div style="align-items: center; justify-content: center;">
                <h1>Simplifiez la Transition Énergétique de Votre Flotte</h1>
                <p>Cette plateforme web simplifie la transition d'une flotte d'equipement thermiques vers des equipements électriques en fournissant des recommandations et analyses détaillées. Elle identifie les modèles électriques équivalents, compare la consommation, les coûts d'exploitation, et évalue l'impact environnemental.</p>
                
                <div >
                    <h2>Fonctionnalités principales :</h2>
                    <ul>
                        <li>Saisie des Données : L'utilisateur importe un tableau contenant des informations sur la flotte existante.</li>
                        <li>Analyse Rapide : En quelques secondes, la plateforme génère des résultats détaillés.</li>
                        <li>Analyse Avancée : Grâce à l’intelligence artificielle, la plateforme fournit une analyse approfondie des données.</li>
                    </ul>
                </div>
            </div>
            """)

        with gr.Tab("Importer les données"):
            vehicle_data_file = gr.File(label="Importer les données des véhicules")
            charging_station_file = gr.File(label="Importer les données des stations de recharge")
            electric_vehicle_file = gr.File(label="Importer les données des véhicules électriques")
            vehicle_data, charging_station_data, electric_vehicle_data, table1, table2, table3, table4, table5, table6 = gr.State(), gr.State(), gr.State(), gr.State(), gr.State(), gr.State(), gr.State(), gr.State(), gr.State()
            # Initialisation des DataFrames avec des DataFrames vides
            #table1 = gr.DataFrame(pd.DataFrame(), label="Tableau 1")
            #table2 = gr.DataFrame(pd.DataFrame(), label="Tableau 2")
            success_message = gr.Markdown("")
            gr.Button("Importer et traiter").click(
                upload_and_process_files, 
                inputs=[vehicle_data_file, charging_station_file, electric_vehicle_file],
                outputs=[vehicle_data, charging_station_data, electric_vehicle_data, table1, table2, table3, table4, table5, table6, success_message]
            )
        
        # Onglet pour afficher et analyser les tableaux
        with gr.Tab("Tableaux") as afficher_onglet:
            gr.Markdown("### Tableau 1 : Données obtenues de la part du client")
            tableau1_affiche = gr.DataFrame(label="")
            download_table1_btn = gr.File(label="Télécharger Tableau 1 en CSV")


            gr.Markdown("### Tableau 2 : Consommation et autonomie des véhicules électriques")
            tableau2_affiche = gr.DataFrame(label="")
            download_table2_btn = gr.File(label="Télécharger Tableau 2 en CSV")

            gr.Markdown("### Tableau 3 : Année de conversion des véhicules thermiques")
            tableau3_affiche = gr.DataFrame(label="")
            download_table3_btn = gr.File(label="Télécharger Tableau 3 en CSV")

            gr.Markdown("### Tableau 4 : Réduction des GES (tonnes) par année")
            tableau4_affiche = gr.DataFrame(label="")
            download_table4_btn = gr.File(label="Télécharger Tableau 4 en CSV")
            # Lorsque l'onglet "Afficher les Tableaux" est sélectionné, les tableaux sont affichés automatiquement
            """ afficher_onglet.select(
                upload_and_process_files, 
                inputs=[vehicle_data_file, charging_station_file, electric_vehicle_file],
                outputs=[tableau1_affiche, tableau2_affiche]
            )
 """
            # Lorsque l'onglet "Afficher les Tableaux" est sélectionné, les tableaux et les liens de téléchargement sont générés automatiquement
            def afficher_onglet_action(vehicle_data_file, charging_station_file, electric_vehicle_file):
                vehicle_data_file, charging_station_file, electric_vehicle_file, table1, table2, table3, table4, table5, table6, message = upload_and_process_files(vehicle_data_file, charging_station_file, electric_vehicle_file)
                download1_path = download_table_as_csv(table1)
                download2_path = download_table_as_csv(table2)
                download3_path = download_table_as_csv(table3)
                download4_path = download_table_as_csv(table4)
                return table1, table2, table3, table4, download1_path, download2_path, download3_path, download4_path
            
            afficher_onglet.select(
                afficher_onglet_action, 
                inputs=[vehicle_data_file, charging_station_file, electric_vehicle_file],
                outputs=[tableau1_affiche, tableau2_affiche, tableau3_affiche, tableau4_affiche, download_table1_btn, download_table2_btn, download_table3_btn, download_table4_btn]
            )

        
        with gr.Tab("Scenario") as afficher_onglet:
            gr.Markdown("### Tableau 1 : Scenario d'electrification")
            tableau5_affiche = gr.DataFrame(label="")
            download_table5_btn = gr.File(label="Télécharger Tableau 1 en CSV")

            # Lorsque l'onglet "Afficher les Tableaux" est sélectionné, les tableaux et les liens de téléchargement sont générés automatiquement
            def afficher_onglet_action(vehicle_data_file, charging_station_file, electric_vehicle_file):
                vehicle_data_file, charging_station_file, electric_vehicle_file, table1, table2, table3, table4, table5, table6,  message = upload_and_process_files(vehicle_data_file, charging_station_file, electric_vehicle_file)
                download5_path = download_table_as_csv(table1)
                
                return table5, download5_path
            
            afficher_onglet.select(
                afficher_onglet_action, 
                inputs=[vehicle_data_file, charging_station_file, electric_vehicle_file],
                outputs=[tableau5_affiche, download_table5_btn]
            )

        
        with gr.Tab("Optimisation") as afficher_onglet:
            gr.Markdown("### Tableau 1 : Donnees pour l'optimisation")
            tableau6_affiche = gr.DataFrame(label="")
            download_table6_btn = gr.File(label="Télécharger Tableau 1 en CSV")

            # Lorsque l'onglet "Afficher les Tableaux" est sélectionné, les tableaux et les liens de téléchargement sont générés automatiquement
            def afficher_onglet_action(vehicle_data_file, charging_station_file, electric_vehicle_file):
                vehicle_data_file, charging_station_file, electric_vehicle_file, table1, table2, table3, table4, table5, table6, message = upload_and_process_files(vehicle_data_file, charging_station_file, electric_vehicle_file)
                download6_path = download_table_as_csv(table1)
                
                return table6, download6_path
            
            afficher_onglet.select(
                afficher_onglet_action, 
                inputs=[vehicle_data_file, charging_station_file, electric_vehicle_file],
                outputs=[tableau6_affiche, download_table6_btn]
            )


        with gr.Tab("Graphiques"):
            with gr.Tabs():
                with gr.Tab("Graphique 1 - Heure de Fonctionnement par jours"):
                    gr.Markdown("### Heure de Fonctionnement par jours")
                    gr.Plot(plot_png1, inputs=vehicle_data)
                
                with gr.Tab("Graphique 2 - Consommation et Capacité de batterie"):
                    gr.Markdown("### Consommation vs Capacité")
                    gr.Plot(plot_png, inputs=vehicle_data)
                
                with gr.Tab("Graphique 3 - Temps de recharge en heure"):
                    gr.Markdown("### Temps de recharge")
                    gr.Plot(plot_png2, inputs=vehicle_data)
            
    return demo

demo = gradio_app()
demo.launch()

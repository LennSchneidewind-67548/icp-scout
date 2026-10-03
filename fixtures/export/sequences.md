# Outreach sequences for Helio Desk

Drafted by the model in French from the recorded evidence, with a English translation under each touch. Nothing has been sent. Touches: email 1 (day 0), email 2 (day 3), LinkedIn connection note (day 6).

## HubSpot column map

Two imports. First `hubspot_companies.csv`, one object (Companies); create the new properties while mapping. Then `hubspot_contacts.csv`, one file with two objects (Contacts and Companies): map `Company Domain Name` to the Company, which matches the company imported first and associates the contact.

| Column | Object | Property |
|---|---|---|
| `Company name` | Company | Name |
| `Company Domain Name` | Company | Company Domain Name (the dedupe key) |
| `Company phone` | Company | Phone Number |
| `Street Address` | Company | Street Address |
| `City` | Company | City |
| `Postal Code` | Company | Postal Code |
| `Country/Region` | Company | Country/Region |
| `Number of Employees` | Company | Number of Employees |
| `icp_score` | Company | new property, number |
| `icp_tier` | Company | new property, single-line text |
| `icp_queue_rank` | Company | new property, number |
| `icp_reason` | Company | new property, multi-line text |
| `icp_evidence` | Company | new property, multi-line text |
| `icp_group_sirens` | Company | new property, single-line text |
| `rge_email` | Company | new property, single-line text |
| `icp_registry_name` | Company | new property, single-line text |
| `seq_1_subject` | Company | new property, single-line text |
| `seq_1_body` | Company | new property, multi-line text |
| `seq_2_body` | Company | new property, multi-line text |
| `seq_3_linkedin` | Company | new property, multi-line text |
| `First Name` | Contact | First Name |
| `Last Name` | Contact | Last Name |
| `Job Title` | Contact | Job Title |

## 1. Brise Marine Energies

- Score 10.0, tier A: ~74 staff | installs both heat pumps and solar | hiring for sales, planning or install roles, or opening sites | online configurator, lead forms, a crm or a competing tool in use
- Domain: brise-marine.example
- Contact: Yann Kerjean, Gérant (managing director)

Hook: «Nous recrutons : technicien installateur pompe a chaleur (CDI, Quimper)» (We are hiring: heat pump installation technician (permanent, Quimper)) https://www.brise-marine.example/recrutement

### Email 1, day 0: Vos recrutements de techniciens PAC

*Subject (English): Your heat pump technician hiring*

> Bonjour,
>
> Vous écrivez « Nous recrutons : technicien installateur pompe a chaleur ». Chaque nouveau technicien, ce sont plus de devis à chiffrer. Helio Desk réunit CRM, dimensionnement et devis au même endroit. Comment vos devis sont-ils faits aujourd'hui ?
>
> Si ce n'est pas le sujet, dites-le-moi et je n'écrirai plus.

*English:*

> Hello,
>
> You write "We are hiring: heat pump installation technician". Every new technician means more quotes to price. Helio Desk brings CRM, system sizing and quoting into one place. How are your quotes done today?
>
> If this isn't a topic for you, tell me and I won't write again.

### Email 2, day 3

> Bonjour,
>
> Vous posez du photovoltaïque et des pompes à chaleur : deux dimensionnements, un seul devis avec Helio Desk. Un échange de 15 minutes ?
>
> Un simple « non » suffit pour ne plus recevoir de message.

*English:*

> Hello,
>
> You install solar PV and heat pumps: two system sizings, one quote with Helio Desk. A 15-minute call?
>
> A simple "no" is enough to stop these messages.

### LinkedIn, day 6

> Bonjour, je travaille chez Helio Desk, un outil de devis pour installateurs PAC et solaire. J'ai vu vos recrutements : ravi d'échanger.

*English:*

> Hello, I work at Helio Desk, a quoting tool for heat pump and solar installers. I saw your hiring: happy to connect.

## 2. Cap Horizon Solaire

- Score 7.3, tier B: installs both heat pumps and solar | online configurator, lead forms, a crm or a competing tool in use | weakest: hiring for sales, planning or install roles, or opening sites
- Domain: caphorizon-solaire.example
- Contact: Luc Roche, Gérant (managing director)

Hook: «photovoltaique, pompes a chaleur et bornes de recharge» (solar PV, heat pumps and EV chargers) https://www.caphorizon-solaire.example

### Email 1, day 0: Votre activité solaire

*Subject (English): Your solar business*

> Bonjour,
>
> Vous installez des panneaux photovoltaïques. Helio Desk réunit le suivi des prospects, l'étude et le devis dans un seul outil. Combien de devis faites-vous par mois ?
>
> Si ce n'est pas le sujet, dites-le-moi et je n'écrirai plus.

*English:*

> Hello,
>
> You install solar PV panels. Helio Desk brings lead follow-up, the system study and the quote into one tool. How many quotes do you do a month?
>
> If this isn't a topic for you, tell me and I won't write again.

### Email 2, day 3

> Bonjour,
>
> Votre simulateur solaire en ligne amène des demandes : Helio Desk les range dans un CRM sans ressaisie. Un échange de 15 minutes ?
>
> Un « non » suffit pour ne plus recevoir de message.

*English:*

> Hello,
>
> Your online solar simulator brings in requests: Helio Desk files them in a CRM with no re-typing. A 15-minute call?
>
> A "no" is enough to stop these messages.

### LinkedIn, day 6

> Bonjour, je travaille chez Helio Desk, un outil de devis pour installateurs solaires. Ravi d'échanger.

*English:*

> Hello, I work at Helio Desk, a quoting tool for solar installers. Happy to connect.

## 3. Vallon Thermique

- Score 5.0, tier C: installs both heat pumps and solar | weakest: hiring for sales, planning or install roles, or opening sites
- Domain: (none: HubSpot cannot dedupe this row or associate its contact)
- Contact: Aurélie Durandal, Gérant (managing director)

Hook: «Pompe a chaleur : chauffage ; Panneaux solaires photovoltaiques» (Heat pump: heating; solar PV panels) https://annuaire-entreprises.data.gouv.fr/entreprise/900000060

### Email 1, day 0: Pompes à chaleur et devis

*Subject (English): Heat pumps and quotes*

> Bonjour,
>
> Votre entreprise est certifiée RGE pour les pompes à chaleur. Helio Desk aide les installateurs à passer de la visite au devis signé plus vite. Est-ce un sujet pour vous ?
>
> Si non, dites-le-moi et je n'écrirai plus.

*English:*

> Hello,
>
> Your company is RGE-certified for heat pumps. Helio Desk helps installers go from the site visit to a signed quote faster. Is this a topic for you?
>
> If not, tell me and I won't write again.

### Email 2, day 3

> Bonjour,
>
> Un devis PAC demande un dimensionnement précis. Helio Desk le calcule à partir de la visite. Je vous montre en 15 minutes ?
>
> Un « non » suffit pour ne plus recevoir de message.

*English:*

> Hello,
>
> A heat pump quote needs a precise system sizing. Helio Desk works it out from the site visit. Shall I show you in 15 minutes?
>
> A "no" is enough to stop these messages.

### LinkedIn, day 6

> Bonjour, je travaille chez Helio Desk, un outil pour installateurs de pompes à chaleur. Ravi d'échanger avec vous.

*English:*

> Hello, I work at Helio Desk, a tool for heat pump installers. Happy to connect with you.

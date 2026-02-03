# apps/core/defaults.py

SERVICE_DEFAULTS = {
    'air_ticket': {
        'short_description': "Confirmed, non-changeable departure date and time.",
        'description': (
            "A fixed departure flight ticket refers to an airline ticket with a confirmed, non-changeable departure date and time. "
            "Once booked, the flight schedule is locked, and changes or cancellations are usually not allowed or come with high penalties. "
            "These tickets are commonly offered at lower prices compared to flexible fares and are ideal for travelers with definite travel plans. "
            "Fixed departure tickets ensure seat availability on a specific flight and help airlines manage capacity efficiently."
        ),
        'features': [
            "Fixed Schedule",
            "Confirmed Seat Availability",
            "Optimized Capacity Management",
            "Cost-Effective Fare"
        ],
        'inclusions': ["Seat Guarantee", "Airport Taxes"],
        'exclusions': ["Change Fees", "Cancellation Refunds", "Personal Expenses"]
    },
    'visa': {
        'short_description': "Umrah Visa - Duration of Stay: 90 days, Single Entry.",
        'description': (
            "Umrah Visa Details:\n"
            "- Duration of Stay: 90 days\n"
            "- Number of Entry: Single\n\n"
            "DOCUMENTS REQUIRED:\n"
            "- Passport scan copy with at least 6 months validity from exit date.\n"
            "- PAN card copy (for Indian applicants).\n"
            "- Confirmed roundtrip air ticket.\n\n"
            "MANDATORY REQUIREMENTS:\n"
            "- Hotel booking must be made only from listed Nusuk Masar platform.\n"
            "- Approved transport arrangements are required.\n\n"
            "Note: Processing time is 02 to 03 working days. We do not provide work/employment visas."
        ),
        'features': ["90-day Duration", "Single Entry", "Quick Processing"],
        'inclusions': ["Visa Processing Fee", "Insurance"],
        'exclusions': ["Personal Courier Charges", "Rejection-related Loss"]
    },
    'hotel': {
        'short_description': "Strategic luxury and mid-range hotel inventories in Makkah, Madinah, and Riyadh.",
        'description': (
            "Saudi Arabia has 13 provinces with Riyadh, Makkah, Jeddah, and Madinah as strategic hubs. "
            "Makkah and Madinah have huge hotel inventories focused on pilgrimage (Hajj/Umrah), "
            "with a growing mix of luxury and mid-range properties. Business travel is anchored in "
            "Riyadh, Jeddah and the Eastern Province."
        ),
        'features': ["Luxury & Mid-range mix", "Pilgrimage Centrality", "Diversified Tourism"],
        'inclusions': ["Inventory Management", "Heritage Proximity"],
        'exclusions': ["Room Service Charges", "Laundry"]
    },
    'umrah_guide': {
        'short_description': "Assistance for religious guidance, rituals, and travel coordination.",
        'description': (
            "An Umrah tour guide assists pilgrims throughout their journey by providing religious guidance, "
            "coordinating travel activities, and ensuring rituals (Ihram, Tawaf, Sa’i, Halq/Qasar) are performed correctly and safely."
        ),
        'features': [
            "Religious Ritual Guidance",
            "Schedule Coordination",
            "Elderly Assistance",
            "Emergency Coordination"
        ],
        'inclusions': ["Guide Expertise", "Group Management"],
        'exclusions': ["Personal Tips", "Personal Shopping Assistance"]
    },
    'food': {
        'short_description': "International cuisine mix including Arab, South Asian, and Continental options.",
        'description': (
            "Cuisine mix is very international. Hotels typically serve buffet-style menus with Arab food (Kabsa, Grill), "
            "South Asian food (Curry, Biryani), and Continental options (Pasta, Eggs). "
            "Dates and Zamzam water are almost always available, especially during Ramadan."
        ),
        'features': ["Buffet & Set Meals", "Ramadan Suhoor/Iftar Support", "Halal Standard"],
        'inclusions': ["Standard Meals", "Zamzam Water Access"],
        'exclusions': ["Extra A La Carte Orders", "Special Drinks"]
    },
    'transport': {
        'short_description': "Reliable airport transfers, intercity travel, and Ziyarat local sightseeing.",
        'description': (
            "Agent-managed transport includes Airport transfers (Jeddah/Madinah), Intercity travel (Makkah to Madinah), "
            "and Ziyarat sightseeing for holy sites. Vehicles range from Sedan/GMC to buses and vans."
        ),
        'features': ["Airport Pick-up", "Ziyarat Dedicated Trips", "Hotel Shuttle Services"],
        'inclusions': ["Fuel Charges", "Driver Services"],
        'exclusions': ["Waiting Time Penalties", "Extra Stops"]
    },
    'laundry': {
        'short_description': "Convenient, hygienic cleaning solutions for Ihram and everyday clothes.",
        'description': (
            "Services include wash, dry, fold, ironing, and dry cleaning for garments like Ihram, Abayas, and Thobes. "
            "Provider-proximate to Haramain areas with quick turnaround times."
        ),
        'features': ["Hygienic Fabric Care", "Quick Turnaround", "Modest Handling"],
        'inclusions': ["Standard Washing", "Ironing"],
        'exclusions': ["Stain Removal Liability", "Delivery Outside Specified Area"]
    },
    'umrah_kit': {
        'short_description': "Essential items including Ihram, prayer mat, toiletries, and guide books.",
        'description': (
            "Standard Umrah Kit includes Ihram (men), Ihram belt, slipper bag, prayer mat, "
            "Dua/Umrah guide book, tasbeeh, and basic toiletries."
        ),
        'features': ["Complete Ritual Support", "Portable Document Pouch"],
        'inclusions': ["Ihram", "Toiletries", "Document Pouch"],
        'exclusions': ["Extra Clothing", "Medicines"]
    }
}

PACKAGE_DEFAULTS = {
    'umrah': {
        'short_description': "Standard Umrah package with end-to-end assistance.",
        'description': "Complete Umrah journey with guidance, standardized transport, and diverse food options.",
        'features': ["Spiritual Guidance", "Haram Proximity Hotels", "Standard Transport"],
        'inclusions': ["Visa Processing", "Hotel Accommodation", "Standard Meals", "Transport"],
        'exclusions': ["Personal Shopping", "Extra Ziyarat", "Medical Insurance Extensions"],
        'itinerary': [
            {"day": 1, "title": "Arrival & Transfer", "description": "Arrival at Airport, transfer to hotel and Makkah rituals coordination."},
            {"day": 2, "title": "Makkah Rituals", "description": "Perform Umrah under guidance and attend prayers at Masjid al-Haram."},
            {"day": 3, "title": "Makkah Ziyarat", "description": "Visit Mina, Arafat, Muzdalifah, and holy mountains."},
            {"day": 7, "title": "Transfer to Madinah", "description": "Travel from Makkah to Madinah via private coach or train."},
            {"day": 8, "title": "Madinah Ziyarat", "description": "Visit Masjid Quba, Uhud, and local date markets."}
        ]
    },
    'hajj': {
        'short_description': "Comprehensive Hajj package with premium tent services and guidance.",
        'description': "Full Hajj services including Mina/Arafat tents, catering, transport, and religious supervision.",
        'features': ["Premium Mina Tents", "Religious Supervision", "Full Board Catering"],
        'inclusions': ["Hajj Visa", "Tent Accommodation", "Internal Transport", "All Meals"],
        'exclusions': ["Qurbani (Hadi)", "Personal Laundry", "Extra Luggage Charges"],
        'itinerary': [
            {"day": 1, "title": "Arrival", "description": "Arrival at Jeddah/Makkah and check-in to accommodation."},
            {"day": 8, "title": "Mina Move", "description": "Move to Mina for the start of Hajj rituals."},
            {"day": 9, "title": "Arafat & Muzdalifah", "description": "Standing at Arafat and overnight stay at Muzdalifah."},
            {"day": 10, "title": "Jamarat & Tawaf", "description": "Stoning at Jamarat and performing Tawaf al-Ifadah."},
            {"day": 13, "title": "Madinah Transfer", "description": "Transfer to Madinah after completing Hajj rituals."}
        ]
    },
    'both': {
        'short_description': "Combined Hajj and Umrah services for a complete spiritual journey.",
        'description': "Extended spiritual package covering both Hajj and Umrah performace with high-standard logistics.",
        'features': ["Dual Guidance", "Extended Hotel Stay", "Inter-city Logistics"],
        'inclusions': ["All Visas", "Hotels in Makkah & Madinah", "Full Board", "Luxury Transport"],
        'exclusions': ["Personal Incidentals", "Optional Sightseeing Tours"],
        'itinerary': [
            {"day": 1, "title": "Umrah Phase", "description": "Arrival and performance of Umrah rituals."},
            {"day": 10, "title": "Hajj Preparation", "description": "Religious seminars and preparation for Hajj move."},
            {"day": 15, "title": "Main Hajj Rituals", "description": "Execution of all Hajj manasik as per Sunnah."},
            {"day": 20, "title": "Madinah Stay", "description": "Extended stay in Madinah for prayers and ziyarat."}
        ]
    },
    'zyarat': {
        'short_description': "Detailed Ziyarat tour exploring holy and historical sites in Makkah and Madinah.",
        'description': "Guided tours to Jannat al-Mu'alla, Cave Hira, Cave Thawr, Battlegrounds, and historic mosques.",
        'features': ["Expert Historian Guide", "Door-to-door Transport", "Entrance Coordination"],
        'inclusions': ["Tour Guide", "Air-conditioned Vehicle", "Refreshments"],
        'exclusions': ["Main Meals", "Sacrificial Offerings", "Personal Donations"],
        'itinerary': [
            {"day": 1, "title": "Makkah Sites", "description": "Cave Hira, Cave Thawr, and graves of prominent Sahaba."},
            {"day": 2, "title": "Battlegrounds", "description": "Visits to Uhud, Khandaq, and Qiblatain Mosques."},
            {"day": 3, "title": "Museums", "description": "Prophet's Mosque Museum and local heritage centers."}
        ]
    },
    'ramzan': {
        'short_description': "Specialized Ramadan package with Suhoor/Iftar services and Taraweeh coordination.",
        'description': "Experience the spirituality of Ramadan in Haramain with dedicated meal plans and proximity hotels.",
        'features': ["Iftar/Suhoor Buffet", "Haram Proximity", "Taraweeh Support"],
        'inclusions': ["Visa", "Stay near Haram", "Special Ramadan Meals"],
        'exclusions': ["Eid Gift Items", "Premium Perfumes", "Personal Charity"],
        'itinerary': [
            {"day": 1, "title": "Check-in", "description": "Arrival and first Iftar in the holy city."},
            {"day": 15, "title": "Spiritual peak", "description": "Participation in nightly prayers and Quran recitations."},
            {"day": 29, "title": "Moon Sighting", "description": "Preparation for Eid-ul-Fitr and final prayers."}
        ]
    }
}

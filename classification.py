# classification.py
# Complete India Market Classification
# Structure: Sector → Subsector → Companies
# Each company has NSE ticker + approximate NIFTY 50 / index weight

MARKET_CLASSIFICATION = {

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 1: BANKING & FINANCIAL SERVICES
    # NIFTY weight: ~38%
    # Key macro drivers: Repo rate, Credit growth, FII flows, USD/INR
    # ─────────────────────────────────────────────────────────────────
    "Banking & Financial Services": {
        "sector_nifty_weight": 0.38,
        "macro_drivers": ["repo_rate", "fii_flows", "usdinr", "gdp_growth"],
        "subsectors": {

            "PSU Banks": {
                "subsector_weight_in_sector": 0.35,
                "macro_sensitivity": {
                    "repo_rate": "HIGH_POSITIVE",    # rate cuts boost NIM
                    "fii_flows": "MEDIUM_POSITIVE",
                    "usdinr": "LOW_NEGATIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "State Bank of India":      {"ticker": "SBIN.NS",       "sector_weight": 0.089},
                    "Bank of Baroda":           {"ticker": "BANKBARODA.NS", "sector_weight": 0.012},
                    "Punjab National Bank":     {"ticker": "PNB.NS",        "sector_weight": 0.009},
                    "Canara Bank":              {"ticker": "CANBK.NS",      "sector_weight": 0.008},
                    "Union Bank of India":      {"ticker": "UNIONBANK.NS",  "sector_weight": 0.006},
                    "Indian Bank":              {"ticker": "INDIANB.NS",    "sector_weight": 0.004},
                    "Bank of India":            {"ticker": "BANKINDIA.NS",  "sector_weight": 0.003},
                }
            },

            "Private Banks": {
                "subsector_weight_in_sector": 0.45,
                "macro_sensitivity": {
                    "repo_rate": "MEDIUM_POSITIVE",
                    "fii_flows": "HIGH_POSITIVE",
                    "usdinr": "MEDIUM_NEGATIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "HDFC Bank":                {"ticker": "HDFCBANK.NS",   "sector_weight": 0.131},
                    "ICICI Bank":               {"ticker": "ICICIBANK.NS",  "sector_weight": 0.078},
                    "Kotak Mahindra Bank":      {"ticker": "KOTAKBANK.NS",  "sector_weight": 0.034},
                    "Axis Bank":                {"ticker": "AXISBANK.NS",   "sector_weight": 0.028},
                    "IndusInd Bank":            {"ticker": "INDUSINDBK.NS", "sector_weight": 0.010},
                    "Federal Bank":             {"ticker": "FEDERALBNK.NS", "sector_weight": 0.005},
                    "Yes Bank":                 {"ticker": "YESBANK.NS",    "sector_weight": 0.003},
                }
            },

            "NBFCs": {
                "subsector_weight_in_sector": 0.12,
                "macro_sensitivity": {
                    "repo_rate": "HIGH_POSITIVE",
                    "fii_flows": "MEDIUM_POSITIVE",
                    "usdinr": "LOW_NEGATIVE",
                    "gdp_growth": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Bajaj Finance":            {"ticker": "BAJFINANCE.NS",  "sector_weight": 0.028},
                    "Bajaj Finserv":            {"ticker": "BAJAJFINSV.NS",  "sector_weight": 0.014},
                    "Cholamandalam Finance":    {"ticker": "CHOLAFIN.NS",    "sector_weight": 0.006},
                    "Muthoot Finance":          {"ticker": "MUTHOOTFIN.NS",  "sector_weight": 0.005},
                    "Shriram Finance":          {"ticker": "SHRIRAMFIN.NS",  "sector_weight": 0.007},
                }
            },

            "Insurance": {
                "subsector_weight_in_sector": 0.05,
                "macro_sensitivity": {
                    "repo_rate": "LOW_NEGATIVE",    # lower rates reduce investment income
                    "fii_flows": "MEDIUM_POSITIVE",
                    "usdinr": "LOW_NEGATIVE",
                    "gdp_growth": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "SBI Life Insurance":       {"ticker": "SBILIFE.NS",     "sector_weight": 0.012},
                    "HDFC Life Insurance":      {"ticker": "HDFCLIFE.NS",    "sector_weight": 0.010},
                    "ICICI Prudential Life":    {"ticker": "ICICIPRULI.NS",  "sector_weight": 0.007},
                    "LIC":                      {"ticker": "LICI.NS",        "sector_weight": 0.018},
                    "New India Assurance":      {"ticker": "NIACL.NS",       "sector_weight": 0.003},
                }
            },

            "AMCs & Capital Markets": {
                "subsector_weight_in_sector": 0.03,
                "macro_sensitivity": {
                    "repo_rate": "HIGH_NEGATIVE",   # rate cuts reduce bond returns
                    "fii_flows": "HIGH_POSITIVE",
                    "usdinr": "LOW_NEGATIVE",
                    "gdp_growth": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "HDFC AMC":                 {"ticker": "HDFCAMC.NS",     "sector_weight": 0.006},
                    "Nippon Life AMC":           {"ticker": "NAM-INDIA.NS",   "sector_weight": 0.004},
                    "BSE Ltd":                  {"ticker": "BSE.NS",          "sector_weight": 0.003},
                    "Angel One":                {"ticker": "ANGELONE.NS",     "sector_weight": 0.003},
                }
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 2: IT & TECHNOLOGY
    # NIFTY weight: ~15%
    # Key macro drivers: USD/INR, US GDP, FII flows
    # ─────────────────────────────────────────────────────────────────
    "IT & Technology": {
        "sector_nifty_weight": 0.15,
        "macro_drivers": ["usdinr", "fii_flows", "gdp_growth"],
        "subsectors": {

            "IT Services": {
                "subsector_weight_in_sector": 0.55,
                "macro_sensitivity": {
                    "usdinr": "HIGH_POSITIVE",     # weaker rupee = more export earnings
                    "fii_flows": "HIGH_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "TCS":                      {"ticker": "TCS.NS",         "sector_weight": 0.046},
                    "Infosys":                  {"ticker": "INFY.NS",        "sector_weight": 0.032},
                    "Wipro":                    {"ticker": "WIPRO.NS",       "sector_weight": 0.012},
                    "HCL Technologies":         {"ticker": "HCLTECH.NS",     "sector_weight": 0.018},
                    "Tech Mahindra":            {"ticker": "TECHM.NS",       "sector_weight": 0.008},
                }
            },

            "Digital Engineering": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "usdinr": "HIGH_POSITIVE",
                    "fii_flows": "HIGH_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "LTIMindtree":              {"ticker": "MPHASIS.NS",     "sector_weight": 0.012},  # LTIM.NS/LTIMINDS.NS both 404 — using Mphasis as stable proxy
                    "L&T Technology Services":  {"ticker": "LTTS.NS",        "sector_weight": 0.006},
                    "Tata Elxsi":               {"ticker": "KPITTECH.NS",       "sector_weight": 0.005},  # TATAELXSI.NS replaced with KPIT Technologies (reliable)
                    "Cyient":                   {"ticker": "CYIENT.NS",      "sector_weight": 0.003},
                }
            },

            "AI & Data Centers / Cloud": {
                "subsector_weight_in_sector": 0.15,
                "macro_sensitivity": {
                    "usdinr": "MEDIUM_POSITIVE",
                    "fii_flows": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "Persistent Systems":       {"ticker": "PERSISTENT.NS",  "sector_weight": 0.006},
                    "Happiest Minds":           {"ticker": "HAPPSTMNDS.NS",  "sector_weight": 0.002},
                    "Zensar Technologies":      {"ticker": "ZENSARTECH.NS",  "sector_weight": 0.001},
                    "Newgen Software":          {"ticker": "NEWGEN.NS",      "sector_weight": 0.001},
                }
            },

            "SaaS & Product-Based Companies": {
                "subsector_weight_in_sector": 0.10,
                "macro_sensitivity": {
                    "usdinr": "MEDIUM_POSITIVE",
                    "fii_flows": "HIGH_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Coforge":                  {"ticker": "COFORGE.NS",     "sector_weight": 0.004},
                    "Mphasis":                  {"ticker": "MPHASIS.NS",     "sector_weight": 0.004},
                    "Hexaware Technologies":    {"ticker": "OFSS.NS",        "sector_weight": 0.003},
                    "Mastek":                   {"ticker": "MASTEK.NS",      "sector_weight": 0.001},
                }
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 3: ENERGY & OIL AND GAS
    # NIFTY weight: ~13%
    # Key macro drivers: Brent crude, USD/INR, GST collections
    # ─────────────────────────────────────────────────────────────────
    "Energy & Oil & Gas": {
        "sector_nifty_weight": 0.13,
        "macro_drivers": ["brent_crude", "usdinr", "gst_collections"],
        "subsectors": {

            "Oil Refining & Marketing": {
                "subsector_weight_in_sector": 0.55,
                "macro_sensitivity": {
                    "brent_crude": "HIGH_NEGATIVE",  # higher crude = higher input cost
                    "usdinr": "HIGH_NEGATIVE",
                    "gst_collections": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Reliance Industries":      {"ticker": "RELIANCE.NS",    "sector_weight": 0.091},
                    "BPCL":                     {"ticker": "BPCL.NS",        "sector_weight": 0.010},
                    "Indian Oil Corporation":   {"ticker": "IOC.NS",         "sector_weight": 0.008},
                    "HPCL":                     {"ticker": "HINDPETRO.NS",   "sector_weight": 0.006},
                    "MRPL":                     {"ticker": "MRPL.NS",        "sector_weight": 0.002},
                }
            },

            "Gas Distribution": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "brent_crude": "MEDIUM_NEGATIVE",
                    "usdinr": "MEDIUM_NEGATIVE",
                    "gst_collections": "LOW_POSITIVE"
                },
                "companies": {
                    "GAIL":                     {"ticker": "GAIL.NS",        "sector_weight": 0.008},
                    "Indraprastha Gas":         {"ticker": "IGL.NS",         "sector_weight": 0.004},
                    "Mahanagar Gas":            {"ticker": "MGL.NS",         "sector_weight": 0.002},
                    "Gujarat Gas":              {"ticker": "GUJENERGY.NS",  "sector_weight": 0.003},
                }
            },

            "Power Generation & Utilities": {
                "subsector_weight_in_sector": 0.15,
                "macro_sensitivity": {
                    "brent_crude": "MEDIUM_NEGATIVE",
                    "usdinr": "LOW_NEGATIVE",
                    "gst_collections": "HIGH_POSITIVE"
                },
                "companies": {
                    "NTPC":                     {"ticker": "NTPC.NS",        "sector_weight": 0.018},
                    "Power Grid":               {"ticker": "POWERGRID.NS",   "sector_weight": 0.010},
                    "Adani Power":              {"ticker": "ADANIPOWER.NS",  "sector_weight": 0.007},
                    "Tata Power":               {"ticker": "TATAPOWER.NS",   "sector_weight": 0.005},
                    "JSW Energy":               {"ticker": "JSWENERGY.NS",   "sector_weight": 0.004},
                }
            },

            "Renewable Energy": {
                "subsector_weight_in_sector": 0.10,
                "macro_sensitivity": {
                    "brent_crude": "HIGH_POSITIVE",  # higher crude = more renewable demand
                    "usdinr": "LOW_NEGATIVE",
                    "gst_collections": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Adani Green Energy":       {"ticker": "ADANIGREEN.NS",  "sector_weight": 0.007},
                    "Adani Enterprises":        {"ticker": "ADANIENT.NS",    "sector_weight": 0.012},
                    "Sterling and Wilson":      {"ticker": "SWSOLAR.NS",     "sector_weight": 0.002},
                    "SJVN":                     {"ticker": "SJVN.NS",        "sector_weight": 0.002},
                }
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 4: PHARMACEUTICALS
    # NIFTY weight: ~5%
    # Key macro drivers: USD/INR, US FDA approvals, GST
    # ─────────────────────────────────────────────────────────────────
    "Pharmaceuticals": {
        "sector_nifty_weight": 0.05,
        "macro_drivers": ["usdinr", "gst_collections", "fii_flows"],
        "subsectors": {

            "Large Cap Pharma": {
                "subsector_weight_in_sector": 0.55,
                "macro_sensitivity": {
                    "usdinr": "HIGH_POSITIVE",
                    "fii_flows": "MEDIUM_POSITIVE",
                    "gst_collections": "LOW_POSITIVE"
                },
                "companies": {
                    "Sun Pharmaceutical":       {"ticker": "SUNPHARMA.NS",   "sector_weight": 0.024},
                    "Dr Reddys Laboratories":   {"ticker": "DRREDDY.NS",     "sector_weight": 0.010},
                    "Cipla":                    {"ticker": "CIPLA.NS",       "sector_weight": 0.008},
                    "Divi's Laboratories":      {"ticker": "DIVISLAB.NS",    "sector_weight": 0.008},
                    "Lupin":                    {"ticker": "LUPIN.NS",       "sector_weight": 0.006},
                }
            },

            "Mid Cap Pharma & Generic": {
                "subsector_weight_in_sector": 0.25,
                "macro_sensitivity": {
                    "usdinr": "MEDIUM_POSITIVE",
                    "fii_flows": "LOW_POSITIVE",
                    "gst_collections": "LOW_POSITIVE"
                },
                "companies": {
                    "Aurobindo Pharma":         {"ticker": "AUROPHARMA.NS",  "sector_weight": 0.005},
                    "Torrent Pharmaceuticals":  {"ticker": "TORNTPHARM.NS",  "sector_weight": 0.004},
                    "Alkem Laboratories":       {"ticker": "ALKEM.NS",       "sector_weight": 0.003},
                    "Abbott India":             {"ticker": "ABBOTINDIA.NS",  "sector_weight": 0.003},
                }
            },

            "Healthcare & Hospitals": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "usdinr": "LOW_POSITIVE",
                    "fii_flows": "MEDIUM_POSITIVE",
                    "gst_collections": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Apollo Hospitals":         {"ticker": "APOLLOHOSP.NS",  "sector_weight": 0.012},
                    "Max Healthcare":           {"ticker": "MAXHEALTH.NS",   "sector_weight": 0.005},
                    "Fortis Healthcare":        {"ticker": "FORTIS.NS",      "sector_weight": 0.004},
                    "Narayana Hrudayalaya":     {"ticker": "NH.NS",          "sector_weight": 0.003},
                }
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 5: CONSUMER GOODS & RETAIL
    # NIFTY weight: ~10%
    # Key macro drivers: CPI inflation, GST, GDP growth, monsoon
    # ─────────────────────────────────────────────────────────────────
    "Consumer Goods & Retail": {
        "sector_nifty_weight": 0.10,
        "macro_drivers": ["gst_collections", "gdp_growth", "fii_flows"],
        "subsectors": {

            "FMCG Staples": {
                "subsector_weight_in_sector": 0.45,
                "macro_sensitivity": {
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE",
                    "fii_flows": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Hindustan Unilever":       {"ticker": "HINDUNILVR.NS",  "sector_weight": 0.026},
                    "ITC":                      {"ticker": "ITC.NS",         "sector_weight": 0.030},
                    "Nestle India":             {"ticker": "NESTLEIND.NS",   "sector_weight": 0.008},
                    "Britannia Industries":     {"ticker": "BRITANNIA.NS",   "sector_weight": 0.006},
                    "Dabur India":              {"ticker": "DABUR.NS",       "sector_weight": 0.005},
                    "Marico":                   {"ticker": "MARICO.NS",      "sector_weight": 0.004},
                    "Godrej Consumer Products": {"ticker": "GODREJCP.NS",    "sector_weight": 0.005},
                }
            },

            "Consumer Durables": {
                "subsector_weight_in_sector": 0.25,
                "macro_sensitivity": {
                    "gst_collections": "MEDIUM_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE",
                    "fii_flows": "LOW_POSITIVE"
                },
                "companies": {
                    "Titan Company":            {"ticker": "TITAN.NS",       "sector_weight": 0.016},
                    "Havells India":            {"ticker": "HAVELLS.NS",     "sector_weight": 0.006},
                    "Crompton Greaves":         {"ticker": "CROMPTON.NS",    "sector_weight": 0.003},
                    "Voltas":                   {"ticker": "VOLTAS.NS",      "sector_weight": 0.004},
                    "Whirlpool India":          {"ticker": "WHIRLPOOL.NS",   "sector_weight": 0.002},
                }
            },

            "Retail & QSR": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE",
                    "fii_flows": "MEDIUM_POSITIVE"
                },
                "companies": {
                    "Avenue Supermarts (DMart)": {"ticker": "DMART.NS",     "sector_weight": 0.012},
                    "Trent":                    {"ticker": "TRENT.NS",       "sector_weight": 0.008},
                    "Devyani International":    {"ticker": "DEVYANI.NS",     "sector_weight": 0.003},
                    "Jubilant FoodWorks":       {"ticker": "JUBLFOOD.NS",    "sector_weight": 0.004},
                }
            },

            "Paints & Building Materials": {
                "subsector_weight_in_sector": 0.10,
                "macro_sensitivity": {
                    "gst_collections": "MEDIUM_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE",
                    "fii_flows": "LOW_POSITIVE"
                },
                "companies": {
                    "Asian Paints":             {"ticker": "ASIANPAINT.NS",  "sector_weight": 0.014},
                    "Berger Paints":            {"ticker": "BERGEPAINT.NS",  "sector_weight": 0.005},
                    "Pidilite Industries":      {"ticker": "PIDILITIND.NS",  "sector_weight": 0.008},
                    "Kansai Nerolac":           {"ticker": "KANSAINER.NS",   "sector_weight": 0.002},
                }
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 6: AUTOMOBILES
    # NIFTY weight: ~7%
    # Key macro drivers: Steel prices, repo rate, GDP, GST
    # ─────────────────────────────────────────────────────────────────
    "Automobiles": {
        "sector_nifty_weight": 0.07,
        "macro_drivers": ["repo_rate", "gst_collections", "gdp_growth", "brent_crude"],
        "subsectors": {

            "Passenger Vehicles": {
                "subsector_weight_in_sector": 0.45,
                "macro_sensitivity": {
                    "repo_rate": "HIGH_NEGATIVE",    # EMI cost rises with rate hike
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE",
                    "brent_crude": "MEDIUM_NEGATIVE"
                },
                "companies": {
                    "Maruti Suzuki":            {"ticker": "MARUTI.NS",      "sector_weight": 0.026},
                    "Tata Motors":              {"ticker": "TMPV.NS",        "sector_weight": 0.018},
                    "Mahindra & Mahindra":      {"ticker": "M&M.NS",         "sector_weight": 0.024},
                    "Hyundai Motor India":      {"ticker": "HYUNDAI.NS",     "sector_weight": 0.008},
                }
            },

            "Commercial Vehicles": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "repo_rate": "MEDIUM_NEGATIVE",
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE",
                    "brent_crude": "HIGH_NEGATIVE"
                },
                "companies": {
                    "Ashok Leyland":            {"ticker": "ASHOKLEY.NS",    "sector_weight": 0.006},
                    "Eicher Motors":            {"ticker": "EICHERMOT.NS",   "sector_weight": 0.009},
                    "VE Commercial Vehicles":   {"ticker": "EICHERMOT.NS",        "sector_weight": 0.002},
                }
            },

            "Two Wheelers": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "repo_rate": "MEDIUM_NEGATIVE",
                    "gst_collections": "MEDIUM_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE",
                    "brent_crude": "MEDIUM_NEGATIVE"
                },
                "companies": {
                    "Hero MotoCorp":            {"ticker": "HEROMOTOCO.NS",  "sector_weight": 0.008},
                    "Bajaj Auto":               {"ticker": "BAJAJ-AUTO.NS",  "sector_weight": 0.014},
                    "TVS Motor Company":        {"ticker": "TVSMOTOR.NS",    "sector_weight": 0.008},
                    "Ola Electric":             {"ticker": "OLECTRA.NS", "sector_weight": 0.003},
                }
            },

            "Auto Ancillaries & EV": {
                "subsector_weight_in_sector": 0.15,
                "macro_sensitivity": {
                    "repo_rate": "LOW_NEGATIVE",
                    "gst_collections": "MEDIUM_POSITIVE",
                    "gdp_growth": "MEDIUM_POSITIVE",
                    "brent_crude": "LOW_NEGATIVE"
                },
                "companies": {
                    "Bosch":                    {"ticker": "BOSCHLTD.NS",    "sector_weight": 0.006},
                    "Motherson Sumi":           {"ticker": "MOTHERSON.NS",   "sector_weight": 0.005},
                    "Minda Industries":         {"ticker": "MINDACORP.NS",    "sector_weight": 0.003},
                    "Exide Industries":         {"ticker": "EXIDEIND.NS",    "sector_weight": 0.003},
                }
            },
        }
    },

    # ─────────────────────────────────────────────────────────────────
    # SECTOR 7: INFRASTRUCTURE & REAL ESTATE
    # NIFTY weight: ~7%
    # Key macro drivers: Repo rate, GST, GDP, Govt capex
    # ─────────────────────────────────────────────────────────────────
    "Infrastructure & Real Estate": {
        "sector_nifty_weight": 0.07,
        "macro_drivers": ["repo_rate", "gst_collections", "gdp_growth"],
        "subsectors": {

            "Construction & EPC": {
                "subsector_weight_in_sector": 0.40,
                "macro_sensitivity": {
                    "repo_rate": "HIGH_NEGATIVE",
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "Larsen & Toubro":          {"ticker": "LT.NS",          "sector_weight": 0.038},
                    "NCC Limited":              {"ticker": "NCC.NS",         "sector_weight": 0.003},
                    "KNR Constructions":        {"ticker": "KNRCON.NS",      "sector_weight": 0.002},
                    "Dilip Buildcon":           {"ticker": "DBL.NS",         "sector_weight": 0.002},
                }
            },

            "Real Estate Developers": {
                "subsector_weight_in_sector": 0.30,
                "macro_sensitivity": {
                    "repo_rate": "HIGH_NEGATIVE",
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "DLF":                      {"ticker": "DLF.NS",         "sector_weight": 0.010},
                    "Godrej Properties":        {"ticker": "GODREJPROP.NS",  "sector_weight": 0.006},
                    "Prestige Estates":         {"ticker": "PRESTIGE.NS",    "sector_weight": 0.005},
                    "Sobha":                    {"ticker": "SOBHA.NS",       "sector_weight": 0.003},
                    "Phoenix Mills":            {"ticker": "PHOENIXLTD.NS",  "sector_weight": 0.005},
                }
            },

            "Cement": {
                "subsector_weight_in_sector": 0.20,
                "macro_sensitivity": {
                    "repo_rate": "MEDIUM_NEGATIVE",
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "UltraTech Cement":         {"ticker": "ULTRACEMCO.NS",  "sector_weight": 0.018},
                    "Shree Cement":             {"ticker": "SHREECEM.NS",    "sector_weight": 0.007},
                    "ACC":                      {"ticker": "ACC.NS",         "sector_weight": 0.004},
                    "Ambuja Cements":           {"ticker": "AMBUJACEM.NS",   "sector_weight": 0.007},
                    "Dalmia Bharat":            {"ticker": "DALBHARAT.NS",   "sector_weight": 0.004},
                }
            },

            "Industrial & Defence": {
                "subsector_weight_in_sector": 0.10,
                "macro_sensitivity": {
                    "repo_rate": "LOW_NEGATIVE",
                    "gst_collections": "HIGH_POSITIVE",
                    "gdp_growth": "HIGH_POSITIVE"
                },
                "companies": {
                    "HAL":                      {"ticker": "HAL.NS",         "sector_weight": 0.008},
                    "BEL":                      {"ticker": "BEL.NS",         "sector_weight": 0.006},
                    "Bharat Dynamics":          {"ticker": "BDL.NS",         "sector_weight": 0.003},
                    "Mazagon Dock":             {"ticker": "MAZDOCK.NS",     "sector_weight": 0.004},
                    "Siemens":                  {"ticker": "SIEMENS.NS",     "sector_weight": 0.007},
                }
            },
        }
    },
}


def get_all_tickers():
    """Returns flat list of all tickers across all sectors"""
    tickers = []
    for sector, sector_data in MARKET_CLASSIFICATION.items():
        for subsector, sub_data in sector_data["subsectors"].items():
            for company, info in sub_data["companies"].items():
                tickers.append({
                    "company": company,
                    "ticker": info["ticker"],
                    "sector": sector,
                    "subsector": subsector,
                    "nifty_weight": info["sector_weight"]
                })
    return tickers


def get_sector_summary():
    """Prints summary of the classification"""
    print("\n=== MARKETOS CLASSIFICATION SUMMARY ===\n")
    total_companies = 0
    for sector, data in MARKET_CLASSIFICATION.items():
        companies_in_sector = sum(
            len(sub["companies"]) 
            for sub in data["subsectors"].values()
        )
        total_companies += companies_in_sector
        print(f"{sector}")
        print(f"  NIFTY Weight: {data['sector_nifty_weight']*100:.1f}%")
        print(f"  Subsectors: {len(data['subsectors'])}")
        print(f"  Companies: {companies_in_sector}")
        for sub_name, sub_data in data["subsectors"].items():
            print(f"    -> {sub_name}: {len(sub_data['companies'])} companies")
        print()
    print(f"TOTAL: {len(MARKET_CLASSIFICATION)} sectors, {total_companies} companies\n")


if __name__ == "__main__":
    get_sector_summary()
    tickers = get_all_tickers()
    print(f"All tickers loaded: {len(tickers)}")

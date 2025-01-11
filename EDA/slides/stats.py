import os

def generate_spatial_slide():
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Connecting Communities</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/lucide/0.263.1/lucide.min.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: #000000;
            color: #f3f4f6;
            font-family: system-ui, -apple-system, sans-serif;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .slide-container {
            width: 90%;
            max-width: 1200px;
            padding: 2rem;
        }
        .header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .title {
            color: #34d399;
            font-size: 2.5rem;
            font-weight: bold;
            margin: 0;
        }
        .subtitle {
            color: #9ca3af;
            font-size: 1.25rem;
            margin-top: 0.5rem;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1.5rem;
            margin-top: 2rem;
        }
        .card {
            background: #111827;
            border: 1px solid #065f46;
            border-radius: 0.5rem;
            padding: 1.5rem;
        }
        .card-title {
            color: #34d399;
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }
        .card-content {
            color: #d1d5db;
            line-height: 1.6;
        }
        .disclaimer {
            color: #9ca3af;
            font-size: 0.875rem;
            font-style: italic;
            margin-top: 2rem;
            text-align: right;
        }
    </style>
</head>
<body>
    <div class="slide-container">
        <div class="header">
            <i data-lucide="map-pin" style="color: #34d399; width: 2rem; height: 2rem;"></i>
            <div>
                <h1 class="title">Connecting Communities</h1>
                <p class="subtitle">How different cities interact with the district</p>
            </div>
        </div>
        <div class="grid">
            <div class="card">
                <h3 class="card-title">Local Movement</h3>
                <p class="card-content">
                    Be'er Sheva residents regularly move between all three major sites - 
                    the university, hospital, and tech park. This creates a vibrant local 
                    ecosystem where people can easily access education, healthcare, and work.
                </p>
            </div>
            <div class="card">
                <h3 class="card-title">Wider Connections</h3>
                <p class="card-content">
                    Tel Aviv shows a distinctive pattern of professional connections, with a notably 
                    high proportion of visits to the tech park relative to other areas. This suggests 
                    strong business ties and regular professional exchange between the two tech hubs.
                </p>
            </div>
            <div class="card">
                <h3 class="card-title">Nearby Towns</h3>
                <p class="card-content">
                    Suburban communities like Omer and Metar have balanced relationships
                    with all parts of the district. The key Bedouin town of Laqye has exceptionally strong university 
                    connections, suggesting a significant student and staff population. This highlights different ways these 
                    communities engage with the district's resources.
                </p>
            </div>
            <div class="card">
                <h3 class="card-title">Healthcare Hub</h3>
                <p class="card-content">
                    Cities throughout the Negev, including Ofaqim, Dimona, Netivot and Arad, rely heavily on Soroka Hospital, 
                    making frequent healthcare-related visits. This dynamic highlights Soroka's crucial role in regional healthcare access.
                </p>
            </div>
        </div>
        <p class="disclaimer">* These narratives were generated using AI equipped with key statistics</p>
    </div>
    <script>
        lucide.createIcons();
    </script>
</body>
</html>
'''

def generate_stats_slide():
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Origin Patterns</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: #000000;
            color: #f3f4f6;
            font-family: system-ui, -apple-system, sans-serif;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .slide-container {
            width: 95%;
            max-width: 1600px;
            padding: 1rem;
        }
        .title {
            color: #f3f4f6;
            font-size: 2.5rem;
            font-weight: bold;
            margin: 0 0 1rem 0;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.75rem;
        }
        .card {
            background: #111827;
            border: 1px solid #2563eb;
            border-radius: 0.5rem;
            padding: 0.5rem;
        }
        .card-title {
            color: #f3f4f6;
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.25rem;
            margin-bottom: 0.25rem;
        }
        .stat-group {
            display: flex;
            flex-direction: column;
            gap: 0.1rem;
        }
        .stat-value {
            font-size: 1.25rem;
            font-weight: bold;
        }
        .stat-label {
            font-size: 0.8rem;
            color: #9ca3af;
        }
        .bgu { color: #fbbf24; }
        .soroka { color: #ef4444; }
        .gavyam { color: #22d3ee; }
        .total { color: #a78bfa; }
        
        .card-note {
            color: #9ca3af;
            font-size: 0.8rem;
            margin-top: 0.25rem;
            line-height: 1.2;
            border-top: 1px solid #2563eb;
            padding-top: 0.25rem;
        }
    </style>
</head>
<body>
    <div class="slide-container">
        <h1 class="title">Origin Patterns</h1>
        <div class="grid">
            <div class="card">
                <h3 class="card-title">Be'er Sheva</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">19.5k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">14.0k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">3.1k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">36.6k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Core city, drives morning peaks and lunch activity</p>
            </div>

            <div class="card">
                <h3 class="card-title">Rahat</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">2.2k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">1.9k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.3k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">4.4k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Largest Bedouin city, strong education focus</p>
            </div>

            <div class="card">
                <h3 class="card-title">Tel Aviv</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.4k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.3k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.1k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">0.8k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Tech exchange via rail, business connections</p>
            </div>

            <div class="card">
                <h3 class="card-title">Laqye</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">1.8k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.9k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.2k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">2.9k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">High student population, dependent on buses</p>
            </div>

            <div class="card">
                <h3 class="card-title">Dimona</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.9k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">1.2k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.2k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">2.3k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Healthcare focus, steady hospital visits</p>
            </div>

            <div class="card">
                <h3 class="card-title">Ofaqim</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.4k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.7k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.1k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">1.2k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Heavy hospital reliance, regional healthcare hub</p>
            </div>

            <div class="card">
                <h3 class="card-title">Omer</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.5k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.4k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.2k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">1.1k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Balanced usage, high-tech workforce presence</p>
            </div>

            <div class="card">
                <h3 class="card-title">Tel Sheva</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">1.6k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.8k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.2k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">2.6k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Strong university connection, morning peaks</p>
            </div>

            <div class="card">
                <h3 class="card-title">Metar</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.4k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.4k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.2k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">1.0k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">High tech park share, professional community</p>
            </div>

            <div class="card">
                <h3 class="card-title">Arad</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.4k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.6k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.1k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">1.1k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Healthcare priority, strong bus connections</p>
            </div>

            <div class="card">
                <h3 class="card-title">Netivot</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.5k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.6k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.1k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">1.2k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Growing education links, healthcare access</p>
            </div>

            <div class="card">
                <h3 class="card-title">Kiryat Gat</h3>
                <div class="stats-grid">
                    <div class="stat-group">
                        <span class="stat-value bgu">0.3k</span>
                        <span class="stat-label">BGU</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value soroka">0.5k</span>
                        <span class="stat-label">Soroka</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value gavyam">0.1k</span>
                        <span class="stat-label">Gav-Yam</span>
                    </div>
                    <div class="stat-group">
                        <span class="stat-value total">0.9k</span>
                        <span class="stat-label">Total</span>
                    </div>
                </div>
                <p class="card-note">Mixed use pattern, growing tech connections</p>
            </div>
        </div>
    </div>
</body>
</html>
'''

def main():

    # Generate statistics slide
    with open('slides/statistics.html', 'w', encoding='utf-8') as f:
        f.write(generate_stats_slide())
    

    print("- slides/statistics.html")

if __name__ == "__main__":
    main()
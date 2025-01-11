import os

def generate_slide_html():
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Beer Sheva Mobility Study</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            background-color: #000000;
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .slide {
            width: 960px;
            height: 720px;
            padding: 20px;
            position: relative;
            box-sizing: border-box;
            overflow: hidden;
        }
        .title {
            font-size: 48px;
            font-weight: bold;
            margin-bottom: 16px;
            position: relative;
            text-align: center;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 16px;
        }
        .section {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 16px;
        }
        .section-title {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 8px;
            color: #60A5FA;
        }
        .list {
            list-style: none;
            padding: 0;
            margin: 0;
            font-size: 24px;
        }
        .list li {
            display: flex;
            align-items: flex-start;
            margin-bottom: 6px;
        }
        .bullet {
            color: #60A5FA;
            margin-right: 8px;
        }
        .footer {
            position: absolute;
            bottom: 20px;
            right: 20px;
            color: #9CA3AF;
            font-size: 20px;
        }
        svg {
            margin-top: 8px;
        }
    </style>
</head>
<body>
    <div class="slide">
        <h1 class="title"> Beer Sheva Mobility Data</h1>
        
        <div class="grid">
            <div class="section">
                <h2 class="section-title">Primary Data</h2>
                <ul class="list">
                    <li><span class="bullet">•</span>Smartphone GPS data</li>
                    <li><span class="bullet">•</span>High accuracy (few meters)</li>
                    <li><span class="bullet">•</span>Aggregated by Decell </li>
                </ul>
                <div style="display: flex; align-items: center; margin-top: 12px;">
                    <svg width="32" height="32" viewBox="0 0 32 32">
                        <circle cx="16" cy="16" r="15" fill="#10B981" fill-opacity="0.2" stroke="#10B981" stroke-width="1.5"/>
                        <path d="M9 16.5L13.5 21L23 11.5" stroke="#10B981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                    </svg>
                    <span style="margin-left: 12px; font-size: 20px;">Anonymized Data</span>
                </div>
            </div>
            
            <div class="section">
                <h2 class="section-title">Units of Analysis</h2>
                <ul class="list">
                    <li><span class="bullet">•</span>CBS statistical areas</li>
                    <li><span class="bullet">•</span>13 Points of Interest in the Beer Sheva Metro</li>
                </ul>
                <svg width="280" height="90" style="margin-top: 12px;">
                    <defs>
                        <marker id="arrowhead" markerWidth="10" markerHeight="7" 
                            refX="9.5" refY="3.5" orient="auto">
                            <polygon points="0 0, 10 3.5, 0 7" fill="#60A5FA"/>
                        </marker>
                        <linearGradient id="boxGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#60A5FA;stop-opacity:0.2"/>
                            <stop offset="100%" style="stop-color:#60A5FA;stop-opacity:0.1"/>
                        </linearGradient>
                    </defs>
                    
                    <rect x="20" y="15" width="100" height="60" rx="8" 
                        fill="url(#boxGradient)" stroke="#60A5FA" stroke-width="1.5"/>
                    <text x="70" y="50" fill="white" font-size="14" font-weight="500"
                        text-anchor="middle" font-family="Arial">Census Areas</text>
                    
                    <rect x="160" y="15" width="100" height="60" rx="8" 
                        fill="url(#boxGradient)" stroke="#60A5FA" stroke-width="1.5"/>
                    <text x="210" y="50" fill="white" font-size="14" font-weight="500"
                        text-anchor="middle" font-family="Arial">POIs</text>
                    
                    <path d="M 125 35 Q 140 35 155 35" stroke="#60A5FA" stroke-width="1.5" 
                        marker-end="url(#arrowhead)"/>
                    <path d="M 155 55 Q 140 55 125 55" stroke="#60A5FA" stroke-width="1.5" 
                        marker-end="url(#arrowhead)"/>
                </svg>
            </div>
            
            <div class="section">
                <h2 class="section-title">Time Periods</h2>
                <ul class="list">
                    <li><span class="bullet">•</span>Collection Stage 1: Nov 2019 - Feb 2020</li>
                    <li><span class="bullet">•</span>Collection Stage 2: July 2021</li>
                    <li><span class="bullet">•</span>Represents an average weekday</li>
                </ul>
            </div>
            
            <div class="section">
                <h2 class="section-title">Key Features</h2>
                <ul class="list">
                    <li><span class="bullet">•</span>Origin/Destination</li>
                    <li><span class="bullet">•</span>Mode (Car, Bus, Train, Walk, Bike)</li>
                    <li><span class="bullet">•</span>Purpose (Work/Other)</li>
                    <li><span class="bullet">•</span>Time & Frequency</li>
                </ul>
            </div>
        </div>
        
        <div class="footer">Processed by Adalya</div>
    </div>
</body>
</html>
    """

    # Write the HTML file
    output_path = "/Users/noamgal/Downloads" + os.sep + "beer_sheva_mobility_study_slide.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Slide HTML has been generated at: {output_path}")
    print("You can open this HTML file in a browser and take a screenshot for PowerPoint")
    print("Or use a HTML to PowerPoint converter tool")

if __name__ == "__main__":
    generate_slide_html()
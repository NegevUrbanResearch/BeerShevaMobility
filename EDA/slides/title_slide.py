def generate_html():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Large-Scale Mobility Analysis</title>
    
    <!-- Tailwind CSS via CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- Lucide Icons via CDN -->
    <script src="https://unpkg.com/lucide@latest"></script>
    
    <style>
        /* Additional custom styles if needed */
        body {
            margin: 0;
            padding: 0;
        }
    </style>
</head>
<body>
    <div class="bg-black min-h-screen flex flex-col items-center justify-center text-white p-8">
        <!-- Main Content Container -->
        <div class="max-w-4xl w-full space-y-8">
            
            <!-- Icon and Title -->
            <div class="flex items-center space-x-4 mb-6">
                <i data-lucide="bar-chart-3" class="w-12 h-12 text-blue-400"></i>
                <h1 class="text-5xl font-bold tracking-tight">
                    Beer Sheva Mobility Analysis
                </h1>
            </div>
            
            <!-- Subtitle -->
            <p class="text-2xl text-gray-400 max-w-2xl">
                Understanding Regional Movement Patterns Through Data
            </p>
            
            <!-- Bottom Section -->
            <div class="pt-12 flex items-center space-x-2 text-blue-400">
                <i data-lucide="arrow-right" class="w-6 h-6"></i>
                <span class="text-xl font-light">Data-Driven Insights for the Innovation District</span>
            </div>
            
            <!-- Footer -->
            <div class="pt-6 text-sm text-gray-500">
                <div class="max-w-2xl text-right">
                    <p>Presented by NUR Data Science Team</p>
                    <p>January 2025</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Initialize Lucide Icons -->
    <script>
        lucide.createIcons();
    </script>
</body>
</html>"""

    # Write to file
    with open('/Users/noamgal/Downloads/mobility_analysis_slide.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

if __name__ == "__main__":
    generate_html()
    print("HTML file has been generated as '/Users/noamgal/Downloads/mobility_analysis_slide.html'")
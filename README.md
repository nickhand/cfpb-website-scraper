# CFPB Website Scraper

Scraping and archiving the CFPB website. The mirrored site is available at [http://cfpb-website-mirror.netlify.app](http://cfpb-website-mirror.netlify.app).

This code recursively searches the source HTML code for [consumerfinance.gov](consumerfinance.gov), extracts links to all HTML pages, data files, and JS, CSS, and other static assets. It runs the scraping process on AWS in parallel. 

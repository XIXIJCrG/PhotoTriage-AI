# Security Policy

## Supported Versions

This project is currently an early prototype. Security fixes are handled on the main branch until the first tagged release.

## Reporting a Vulnerability

Please do not open public issues for secrets, privacy leaks, or vulnerabilities involving photo data.

Report privately through GitHub's private vulnerability reporting if enabled, or contact the maintainer directly.

## Data Handling

PhotoTriage AI can send resized photos to a configured model endpoint. Local mode keeps analysis on your own machine when the endpoint is local. Cloud mode sends image data to the configured API provider and should only be used for photos you are comfortable uploading.

Do not commit API keys, local model paths, private photos, generated CSV files, or XMP metadata from real shoots.

# Schmitz Lab Website

Source codes for the website of the **Schmitz Lab** at the University of Delaware. We study Clp proteases and proteostasis in mycobacteria using structural biology, biochemistry, and molecular microbiology. Alongside the bench work, we are expanding our computational and bioinformatics effort, by combining structure prediction, structural comparison, and experimental validation to generate and test hypotheses about protein function.

**Live site:** https://krs-lab.github.io/schmitz-lab-site/

## Built with

- [Hugo](https://gohugo.io/) static site generator, extended edition, pinned to v0.123.7 in the deploy workflow
- Custom theme: `themes/schmitz-lab-theme`
- SCSS for styling (`assets/scss`)
- Hosted on GitHub Pages, deployed with GitHub Actions (`.github/workflows`)

## Run locally

1. Install [Hugo extended](https://gohugo.io/installation/) v0.123.7, the same version the deploy workflow uses, so local and live builds match.
2. Clone the repo and start the dev server:

   ```bash
   git clone https://github.com/krs-lab/schmitz-lab-site.git
   cd schmitz-lab-site
   hugo server
   ```

3. Open http://localhost:1313/schmitz-lab-site/. The page reloads as you edit. If port 1313 is in use, use the address Hugo prints in the terminal.

To check that the site builds without errors (output goes to `public/`, which is not what gets deployed):

```bash
hugo
```

Use `hugo server` for previewing changes, since a plain build points links at the live site.

## Deployment

Pushing to the `main` branch triggers the "Deploy Hugo site to Pages" workflow (`.github/workflows`), which builds the site with Hugo (`--gc --minify`) and publishes it to GitHub Pages. Changes usually appear within a few minutes.

## Contact

Karl R. Schmitz, PhD, schmitzk@udel.edu  
Departments of Biological Sciences and Department of Chemistry & Biochemistry, University of Delaware, Newark, DE 19716

© Schmitz Lab. All rights reserved.

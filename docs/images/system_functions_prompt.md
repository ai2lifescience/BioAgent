# System functions figure edit prompt

Edited with the built-in `image_gen` tool using the existing figure as the edit target.

Final figure: [system_functions.png](system_functions.png), 1672 × 941 pixels. This revision replaces the six bioinformatics pipeline panels with Genome assembly, Taxonomic identification, Functional annotation, Variant detection, Molecular typing, and Risk assessment. The title, workflow and supporting functions retain their original content and visual style.

## Final edit prompt

Use case: precise-object-edit.
Asset type: existing scientific publication figure, 1672 × 941 pixels.
Input image: EDIT TARGET — docs/images/system_functions.png. Edit this existing figure in place. It is NOT merely a style reference.

PRIMARY REQUEST:
Replace ONLY the contents of the six capability panels under the heading "Bioinformatics pipelines", using the exact six requested headings below. Maintain the original 3-column × 2-row arrangement, the panel boundaries and positions, pastel backgrounds, navy typography, vector-like line artwork, font family, and hierarchy. Make the new illustrations elegant, scientifically clear, balanced and suitable for a computational-biology journal.

CRITICAL UNCHANGED REGIONS:
Preserve the entire top title and four-step workflow, the arrows, all four workflow captions and illustrations, the "Bioinformatics pipelines" heading itself, the entire bottom "Supporting functions" strip with all four icon/label items, the white background, overall image dimensions and margins. Do not redraw or reword any of those regions. Retain all original pixels outside the six panel interiors wherever possible. The six panels are the ONLY edit area, approximately x=36–1637, y=370–822 in the 1672×941 original. Do not crop, shift, rescale, restyle or rearrange the figure.

SIX PANEL CONTENTS, reading order:
1. Top left — exact heading: "Genome assembly"
Caption line 1: "Read assembly"
Caption line 2: "Contig reconstruction"
Illustration: tidy short overlapping sequence-read bars assembling into a few longer aligned contigs, with a single modest internal directional arrow. Match the existing thin strokes and pastel blue/sage scientific illustration style.

2. Top middle — exact heading: "Taxonomic identification"
Caption line 1: "Sequence classification"
Caption line 2: "Reference-based identification"
Illustration: a clean rooted taxonomic branching tree with tiny restrained microbe silhouettes at the tips and a small reference-sequence sheet; scientifically schematic, no numeric values or invented species names.

3. Top right — exact heading: "Functional annotation"
Caption line 1: "Gene prediction"
Caption line 2: "Functional assignment"
Illustration: a short gene-feature track of colored directional blocks beside a matching annotation sheet. Fine navy outlines, muted blue, sage, lavender details.

4. Bottom left — exact heading: "Variant detection"
Caption line 1: "Sequence comparison"
Caption line 2: "Variant calling"
Illustration: three neatly aligned short DNA sequences with a single nucleotide difference marked in restrained color, plus a small variant-results sheet. All rows aligned, no phylogenetic tree necessary.

5. Bottom middle — exact heading: "Molecular typing"
Caption line 1: "Allelic profiles"
Caption line 2: "Sequence-based typing"
Illustration: several aligned small gene-locus blocks forming distinct allele profiles beside a compact classification report. Schematic, elegant, avoid tiny dense text and fake numeric scores.

6. Bottom right — exact heading: "Risk assessment"
Caption line 1: "Resistance-gene screening"
Caption line 2: "Virulence-factor screening"
Illustration: a short sequence with two subtly highlighted features connected to a small checklist report and restrained reference database symbol, matching the original icon style. Represents sequence-based evidence screening, not a clinical diagnosis; no hazard imagery, numerical risk score, treatment claims or alarm colors.

STYLE INVARIANTS:
Keep the same soft powder blue, pale sage/teal and lavender panel colors, deep navy humanist sans-serif text, soft borderless rounded panels, delicate fine consistent outlines, crisp smooth edges. Match original heading and caption sizes, center-align each heading, illustration and caption block, equal panel padding and visual weight. Long headings must be cleanly readable on one line at a consistent size within the panels. Maintain generous whitespace. NO new sections, panel numbering, logos, watermarks, shadows, glossy effects, arrows between the six capability panels, or additional captions.

OUTPUT:
One final complete PNG figure at the original 1672 × 941 dimensions, with the unchanged surrounding artwork and only these six panels replaced. Text must be spelled exactly as supplied.

## Refinement pass — sequence lettering and consistency

The figure was refined with the built-in `image_gen` tool using the current figure as the edit target. The six capability labels, captions, layout, palette, and surrounding workflow/supporting functions were preserved. The risk-assessment sequence was cleaned to use only valid uppercase DNA letters A, C, G, and T, and typography/illustration consistency was improved.

### Refinement prompt

Use the existing `system_functions.png` as the edit target. Preserve its exact 1672 × 941 dimensions, content, six capability labels and captions, panel positions, pastel blue/sage/lavender palette, typography hierarchy, top workflow, section heading, supporting-functions strip, and overall scientific graphical-abstract style. Improve only antialiasing, typography consistency, illustration alignment, and whitespace. In the Risk assessment panel, render a crisp uppercase DNA sequence using only valid A/C/G/T characters with the exact text `...ATGCC  AAGTTC  GCCC...  TTGACA...`; keep the highlighted features and labels `Resistance gene` and `Virulence factor`. Do not add, remove, rename, rearrange, crop, or rescale any content; do not add logos, watermarks, hazard symbols, numeric scores, clinical claims, or extra words.

## Font-color refinement — reference image

The current figure was refined with the built-in `image_gen` tool using [`good font color.png`](good%20font%20color.png) as the font-color reference. The six updated pipeline panels and all content were preserved. Typography, arrows, and text-like linework now use a darker, muted deep navy/slate treatment matching the reference instead of the overly bright saturated blue.

### Refinement constraints

Preserve the exact 1672 × 941 dimensions, title, four-step workflow, six current pipeline labels and captions, panel illustrations, bottom supporting-functions strip, layout, pastel fills, and scientific graphical-abstract style. Change only the typography color treatment and polish. Do not revert the six current panels to the older reference panels, add or remove wording, rearrange content, crop, rescale, add logos, add watermarks, or introduce new decorative elements. Keep the Risk assessment sequence as clean uppercase DNA letters: `...ATGCC  AAGTTC  GCCC...  TTGACA...`.

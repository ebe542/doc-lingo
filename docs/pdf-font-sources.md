# Obtaining fonts for PDF layout reconstruction

Sources checked on 2026-11-08. These are acquisition pages, not automatic
downloads or proof that a current retail font is identical to the PDF's version.
Install fonts yourself, rerun the local font report, and record any substitution.
The manual Scribus font catalog is optional troubleshooting, not a prerequisite.

## Original families in the example PDF

| PDF family / required styles | Source | Acquisition and limitations |
| --- | --- | --- |
| NewBaskerville: Roman, Italic, Bold, BoldItalic | [ITC New Baskerville at MyFonts](https://www.myfonts.com/collections/new-baskerville-font-itc) | Commercial family; select the relevant desktop styles/license. Current Pro names may differ from the PDF's names. A purchase does not establish identical metrics. |
| FranklinGothic: Demi, DemiItal | [Microsoft family information](https://learn.microsoft.com/en-us/typography/font-list/franklin-gothic), [commercial Demi Italic listing](https://www.myfonts.com/products/demi-italic-franklin-gothic-379218) | Microsoft lists Demi and Demi Italic and Office availability. Its information page is not a free font download. Use a licensed supplying product or the vendor's desktop offering for the required cuts. |
| HumanistMann521-BoldCondensed-Bold | [Bitstream Humanist 521 at MyFonts](https://www.myfonts.com/collections/humanist-521-font-bitstream) | Commercial family including Bold Condensed. This is a family-level lead; the exact PDF-specific internal name/version is not verified. |
| Wingdings2 | [Microsoft Wingdings family information](https://learn.microsoft.com/en-us/typography/font-list/wingdings) | Microsoft lists Wingdings 2 and `Wingdng2.ttf`. Obtain through a licensed supplying product or licensing channel. No standalone free download was verified. |

Office cloud availability does not by itself establish availability in Scribus.
See [Microsoft's Office cloud font documentation](https://support.microsoft.com/en-us/office/fonts/cloud-fonts-in-office).
For purchases, check the actual style, desktop use and PDF embedding terms at
checkout. This project neither bundles commercial fonts nor buys them for users.

## Free alternatives to evaluate

These are proposed layout substitutes, **not metrically equivalent replacements**.
They have not yet been visually validated in a reconstructed Scribus page.

| Purpose | Candidate | Download source |
| --- | --- | --- |
| New Baskerville body text | Libre Baskerville, selecting the required available cuts | [Maintainer repository](https://github.com/impallari/Libre-Baskerville), [font files](https://github.com/impallari/Libre-Baskerville/tree/master/fonts) |
| Franklin Gothic headings / captions | Libre Franklin SemiBold or Bold and the corresponding italic cut | [Maintainer repository](https://github.com/impallari/Libre-Franklin), [font files](https://github.com/impallari/Libre-Franklin/tree/master/fonts) |
| Humanist 521 condensed bold labels | DejaVu Sans Condensed Bold as a practical condensed sans-serif trial | [Official DejaVu downloads](https://dejavu-fonts.github.io/Download.html) |

For the Libre families, obtain the repository ZIP through **Code > Download ZIP**
and extract the compiled font files; retain the accompanying license. Prefer
static TTF/OTF cuts for this first experiment: variable-axis selection is not yet
implemented. Do not silently synthesize a missing bold or italic style. For DejaVu,
the official download page offers a TrueType ZIP and its checksum; retain the
[included license](https://dejavu-fonts.github.io/License.html).

Wingdings 2 is a special case: a generic text-font substitution can change the
meaning or appearance of its private-use characters. Preserve the original glyph
as a graphic where supported, or explicitly map it to a visually reviewed symbol.
Do not replace Wingdings 2 with Wingdings merely because both are symbol fonts.
That graphic/symbol reconstruction is still future exporter work.

## Install and verify

1. Follow the source link, choose the required cuts and download the licensed
   desktop font files. Extract ZIP archives first.
2. On Windows, open the TTF/OTF file and choose **Install**, or use the context-menu
   installation option. Install into the account that runs the layout application.
3. Restart the layout application so its font list can refresh.
4. Run a fresh report, using a new output directory:

   ```bash
   python -m scripts.check_pdf_fonts local-data/pdf-layout/extraction-02 \
     --output local-data/pdf-layout/fonts-03
   ```

5. If a font is stored outside the default locations, use `--font-dir` to scan its
   directory. Finding a file there does not install it. Record a replacement using
   the [explicit mapping format](pdf-fonts.md#explicit-mappings).
6. During layout export, verify the actual font selected by the application, text
   wrapping, overflows and overlaps. Availability alone does not validate layout.

Record the source PDF font, chosen family/style, acquisition URL, local file/face
and hash, reason for replacement, and affected pages/blocks. The existing mapping
and font report record file/face choices, hashes and resource pages; acquisition
URL/reason and block-level export decisions still belong in the layout review
notes until the exporter provides its own replacement log.

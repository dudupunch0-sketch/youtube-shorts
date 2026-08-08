# Media acquisition policy

## Scope

The first implementation collects still-image and video candidates for each episode segment. The compositor can later add a slow pan or zoom to a selected still. Automatic generation and automatic rights approval are out of scope for this pass.

## Acquisition order

1. Search an official public API or an openly licensed media index.
2. Verify the original landing page and license metadata.
3. If the source URL is blocked or a normal fetch fails, use the installed `insane-search` skill as an access fallback.
4. Store candidate URLs and provenance in the media manifest, even when the license is unknown.
5. Leave selection and rights judgment to a human. Generation is an explicitly requested, manual fallback only.

For the current noncommercial channel workflow, NamuWiki text captures may be collected as `namuwiki_capture` candidates under CC BY-NC-SA 2.0 KR assumptions. The capture must include the page URL, history URL, capture time, and attribution. Use the contextual capture skill: capture the complete nearest table for structured values, or the complete readable paragraph/list item for explanatory information. This allowance does not automatically cover third-party images embedded in the page.

`insane-search` improves access to a page. It does not make the page or its media reusable.

## Source policy

Prefer public domain, CC0, CC BY, and CC BY-SA assets when the original page confirms the license. Reject or hold for manual review by default:

- unknown or missing license;
- CC BY-NC for a monetized channel;
- CC BY-ND when the asset will be cropped or transformed;
- official copyrighted character art, screenshots, logos, or promotional images;
- assets whose creator or landing page cannot be identified.

Every sourced asset must retain its original URL, landing URL, creator, license, license URL, and attribution text.

## Layouts

- `full_frame`: one selected asset fills the visual area.
- `split_2up`: exactly two selected assets appear left and right with a divider and a shared bottom caption-safe area.

Candidates remain separate provenance records even when they are displayed together. The compositor must not flatten two sources into one provenance-less asset before review.

## Optional generated image policy

If the user explicitly requests generation after collection, generated assets are original editorial illustrations, not copies of supplied Shorts or official key art. Prompts should describe the visual idea and mood rather than reproducing a protected character design. Do not generate text, logos, watermarks, or subtitles inside the image. Use a vertical 9:16 composition with a clear focal subject and negative space for captions.

For fictional-media lore, generated images may use symbolic silhouettes, color contrast, shadows, scales, charts, and abstract scene motifs. Exact official character imagery remains a manual-review choice.

## Manifest states

- `pending`: planned or awaiting a human selection.
- `needs_review`: candidate exists but license, relevance, or copyright risk needs a human decision.
- `approved`: file and provenance passed validation.
- `rejected`: candidate must not enter the video.

The video compositor may consume only `approved` assets.

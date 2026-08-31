# Facilitator runbook

## Before the first group

1. Start SKAetch with `uv run skaetch`.
2. Confirm the opening **Make a radio portrait** screen appears.
3. If a camera will be used, press **Start camera** and allow browser camera
   permission.
4. Press **Use Einstein instead** once to confirm the complete local processing
   path is responsive without depending on the camera.
5. Enter full-screen mode if useful for the exhibit display.

The camera route is optional.  Einstein and Cat are bundled alternatives.
Fornax A and the Crab Nebula are optional local-only examples; their controls
are disabled automatically when those assets are not installed.

## Suggested core interaction

### Make an imaginary radio sky

Choose either a camera image or **Use Einstein instead**.  Explain that the
picture is an imaginary radio-brightness test pattern: SKA-Low would not
literally observe a visible-light portrait.

### AA1 snapshot — 16 stations

Begin with one instant and 120 independent station pairs.  Ask whether the
source is recognisable and use the Fourier-sampling view to connect the poor
image to sparse sampling.

### AA1 after 6 h — introduce Earth rotation

Toggle to six hours.  The same station pairs sweep through additional Fourier
directions as Earth rotates.  Emphasise that this adds information but does not
create the missing baseline diversity of a larger array.

### AA2 — 68 stations

Move forward to AA2.  A recognisable image begins to emerge.  This stage is a
useful reminder that simply adding long baselines is not equivalent to filling
all useful spatial scales.

### AA* — 307 stations

The much richer mixture of short and long spacings recovers substantially more
of the source structure.

### AA4 — 512 stations

Finish with the full staged configuration: 130,816 independent station pairs,
plus Earth rotation, give the densest Fourier sampling and the cleanest Outreach
image in the progression.

With **Animated tracks + After observation**, each six-hour construction state
shows the Fourier tracks accumulating before the new radio image is revealed.

## Facilitator controls

Press **F** to show or hide the facilitator drawer.  It provides:

- Build the SKA or the shorter Build + Earth rotation story;
- direct AA0.5 / AA1 / AA2 / AA* / AA4 access;
- Snapshot / 6 h at every stage;
- Animated tracks / Sampling plot;
- immediate or after-observation image reveal;
- Outreach / Science image mode where supported;
- Camera / Einstein / Fornax A / Crab / Cat sources;
- New image / Back to camera.

Keyboard shortcuts on the main exploration screen are:

- **Left / Right:** previous / next recommended state;
- **R:** toggle Snapshot / 6 h;
- **F:** facilitator controls;
- **Escape:** close facilitator controls.

## Real radio-source examples

When their optional local assets are installed, Fornax A and the Crab Nebula
can be used after the portrait progression to connect the artificial activity
back to radio astronomy.  Fornax A is shown at
an approximately 72-arcmin low-frequency extent; the Crab uses a 6-arcmin
illustrative extent.  These image rasters are brightness templates for the
outreach simulator rather than calibrated simulated SKA observations.

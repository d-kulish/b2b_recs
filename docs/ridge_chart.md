# Weight Distribution Histogram - Ridgeline Chart Clipping Issue

## Overview

This document describes a visualization bug in the Weight Distribution Histogram (ridgeline chart) on the Training tab of the Model Experiments View window, along with the analysis process and recommended fix.

**Location**: `templates/ml_platform/model_experiments.html`
**Function**: `renderWeightHistogramChart()` (line 7239)
**Date**: January 2026

---

## 1. Problem Description

### Observed Behavior

The Weight Distribution Histogram displays epoch-by-epoch weight (or gradient) distributions as a ridgeline plot (also known as a "joy plot"). The chart shows:
- Newer epochs at the bottom (closer to X-axis), displayed in darker orange
- Older epochs at the top, displayed in lighter orange

**The Bug**: Distribution curves for older epochs (at the top of the chart) are visually clipped/cut off. The peaks of distributions for epochs 1, 5, 9, etc. are truncated, making it impossible to see the full shape of the distribution.

### Visual Evidence

In the chart, epoch labels 1, 5, 9... are visible on the right Y-axis, but their corresponding distribution curves have their upper portions cut off by the chart boundary.

### Impact

- Users cannot accurately assess weight distribution changes during early training epochs
- The visualization loses its diagnostic value for detecting initialization issues or early training instabilities
- Comparison between early and late epoch distributions becomes unreliable

---

## 2. Analysis Process

### Step 1: Code Review

Examined the implementation of the ridgeline chart in `model_experiments.html`:

1. **Container Setup** (CSS, lines 2066-2075):
   ```css
   #trainingWeightHistogramChart {
       position: relative;
       height: 300px;
       min-height: 300px;
       width: 100%;
   }
   ```

2. **SVG Margins** (line 7295):
   ```javascript
   const margin = { top: 10, right: 50, bottom: 40, left: 50 };
   ```

3. **Ridge Height Scaling** (lines 7318-7320):
   ```javascript
   const yDensity = d3.scaleLinear()
       .domain([0, maxCount])
       .range([0, height * 0.15]);  // Max ridge height is 15% of chart height
   ```

4. **Epoch Band Positioning** (lines 7322-7326):
   ```javascript
   const yEpoch = d3.scaleBand()
       .domain(d3.range(numEpochs))
       .range([0, height])
       .paddingInner(0);
   ```

5. **Area Generator** (lines 7351-7355):
   ```javascript
   const area = d3.area()
       .x(d => xScale(d.x))
       .y0(0)
       .y1(d => -yDensity(d.y))  // Negative Y = draws UPWARD
       .curve(d3.curveBasis);
   ```

6. **Ridge Transform** (line 7362):
   ```javascript
   .attr('transform', d => `translate(0, ${yEpoch(d.epochIdx) + yEpoch.bandwidth()})`)
   ```

### Step 2: Root Cause Identification

The mathematical conflict:

| Factor | Value |
|--------|-------|
| Chart height | 300px |
| Top margin | 10px |
| Number of epochs (example) | 50 |
| Band height per epoch | 300px / 50 = 6px |
| Max ridge height | 300px * 0.15 = 45px |

**The Problem**:
- Each epoch is allocated ~6px of vertical space (bandwidth)
- But each ridge can extend UP TO 45px vertically (upward from its baseline)
- Epoch 1's baseline is positioned at approximately y=6px
- Its ridge attempts to draw upward to y=-39px (6px - 45px)
- The SVG clips everything above y=0 (the top margin is only 10px)

### Step 3: External Research

Consulted D3.js ridgeline chart documentation and TensorBoard histogram implementation:

- **D3 Graph Gallery**: Standard ridgeline implementations use the transform `translate(0, yName(d.key) - height)` which accounts for the upward extension
- **TensorBoard**: Uses dynamic scaling where ridge heights compress as more epochs are added
- **Data-to-Viz**: Notes that ridgeline plots "hide a part of the data where overlap takes place" - but this refers to intentional overlap, not clipping

---

## 3. Solution Options

### Option A: Increase Top Margin (Simplest)

**Approach**: Increase `margin.top` to accommodate maximum ridge overflow.

```javascript
// Current
const margin = { top: 10, right: 50, bottom: 40, left: 50 };

// Fixed
const maxRidgeHeight = height * 0.15;
const margin = { top: maxRidgeHeight + 10, right: 50, bottom: 40, left: 50 };
```

**Pros**:
- Simple one-line change
- Guarantees no clipping

**Cons**:
- Wastes vertical space when epochs have low peaks
- Fixed overhead regardless of actual data

### Option B: Scale Ridge Height to Band Size

**Approach**: Make ridge height proportional to the available band size rather than a fixed percentage of total height.

```javascript
// Current
const yDensity = d3.scaleLinear()
    .domain([0, maxCount])
    .range([0, height * 0.15]);

// Dynamic scaling based on epochs
const maxRidgeHeight = Math.min(height * 0.15, yEpoch.bandwidth() * 2.5);
const yDensity = d3.scaleLinear()
    .domain([0, maxCount])
    .range([0, maxRidgeHeight]);
```

**Pros**:
- Ridges automatically compress with more epochs
- Maintains visual density
- Mimics TensorBoard behavior

**Cons**:
- Ridges may become very flat with many epochs
- Requires testing to find optimal multiplier

### Option C: Configurable Overlap Factor

**Approach**: Calculate optimal overlap based on number of epochs with user-adjustable parameter.

```javascript
const overlapFactor = 0.8; // Configurable: 0 = no overlap, 1 = full overlap
const bandHeight = height / numEpochs;
const maxRidgeHeight = bandHeight * (1 + overlapFactor * (numEpochs / 10));
```

**Pros**:
- Fine-grained control
- Can be exposed as UI control

**Cons**:
- More complex implementation
- Requires user understanding

### Option D: SVG ClipPath Per Ridge

**Approach**: Use SVG `<clipPath>` elements to explicitly control each ridge's visible area.

```javascript
// Define clip paths for each epoch
svg.append('defs')
    .selectAll('clipPath')
    .data(ridgeData)
    .join('clipPath')
    .attr('id', d => `clip-${d.epochIdx}`)
    .append('rect')
    .attr('x', 0)
    .attr('y', d => -yEpoch.bandwidth() * 3)
    .attr('width', width)
    .attr('height', yEpoch.bandwidth() * 3);
```

**Pros**:
- Precise control over visible area
- Prevents any overflow issues

**Cons**:
- Most complex implementation
- May create visual artifacts at clip boundaries
- Performance overhead with many epochs

---

## 4. Recommended Implementation Plan

### Recommended Approach: Combine Options A + B

This approach provides both safety (adequate margin) and adaptability (dynamic ridge scaling).

### Implementation Steps

#### Step 1: Calculate Dynamic Ridge Height

```javascript
// After calculating yEpoch scale
const bandWidth = yEpoch.bandwidth();

// Ridge height scales inversely with number of epochs
// More epochs = shorter ridges to prevent excessive overlap
const baseRidgeHeight = height * 0.15;  // Original 15%
const scaledRidgeHeight = bandWidth * 2.5;  // 2.5x band height
const maxRidgeHeight = Math.min(baseRidgeHeight, scaledRidgeHeight);

const yDensity = d3.scaleLinear()
    .domain([0, maxCount])
    .range([0, maxRidgeHeight]);
```

#### Step 2: Calculate Dynamic Top Margin

```javascript
// Calculate expected overflow for oldest epoch
const expectedOverflow = maxRidgeHeight;

// Add buffer for visual padding
const dynamicTopMargin = expectedOverflow + 15;

const margin = {
    top: dynamicTopMargin,
    right: 50,
    bottom: 40,
    left: 50
};
```

#### Step 3: Recalculate Dimensions

```javascript
// Ensure height calculation uses new margin
const height = Math.floor(rect.height) - margin.top - margin.bottom;
```

#### Step 4: Update Epoch Label Positioning (if needed)

Verify epoch labels on the right side still align correctly with the new positioning.

### Testing Checklist

- [ ] Test with 10 epochs (few epochs, large bands)
- [ ] Test with 50 epochs (many epochs, small bands)
- [ ] Test with 100+ epochs (extreme case)
- [ ] Verify oldest epoch (epoch 1) peaks are fully visible
- [ ] Verify newest epoch distributions render correctly
- [ ] Test with both Weights and Gradients data types
- [ ] Test with both Query Tower and Candidate Tower
- [ ] Verify epoch labels align with their distributions
- [ ] Check responsiveness when container resizes

### Expected Outcome

After implementation:
1. All epoch distributions will be fully visible without clipping
2. The chart will automatically adapt to different numbers of epochs
3. Visual density will be maintained (ridges overlap appropriately)
4. No wasted space when viewing experiments with few epochs

---

## References

- [D3 Graph Gallery - Ridgeline Basic](https://d3-graph-gallery.com/graph/ridgeline_basic.html)
- [D3 Graph Gallery - Ridgeline Chart](https://d3-graph-gallery.com/ridgeline.html)
- [TensorBoard Histogram Documentation](https://github.com/tensorflow/tensorboard/blob/master/docs/r1/histograms.md)
- [TensorBoard Histogram Plugin](https://github.com/tensorflow/tensorboard/blob/master/tensorboard/plugins/histogram/README.md)
- [Data to Viz - Ridgeline Plot](https://www.data-to-viz.com/graph/ridgeline.html)

# Training configuration reference

`gonzo-train --config PATH` reads a base TrainingConfig as JSON.
`--grid-search PATH` reads a separate grid and combines its candidate values
with that base. Without `--config`, the base is the default TrainingConfig.

## Example files

| File | Contents |
|---|---|
| `experiments/training_config_default.json` | A base config with `model.type` set to `dense` |
| `experiments/sweep_params.json` | Two learning rates and two batch sizes, requesting four Experiments |
| `experiments/dense_sweep.json` | Two learning rates, three batch sizes, two dropout rates, and three hidden-layer lists, requesting 36 Experiments |

The grid files contain only candidate settings. The base config supplies all
other values.

## Grid format

Grid objects follow the TrainingConfig structure. Each leaf is a nonempty list
of candidate values. A Sweep requests every combination of those candidates.
Dotted keys such as `"model.dropout_rate"` are rejected.

```json
{
	"learning_rate": [0.01, 0.001],
	"model": {
		"hidden_layers": [[64, 32], [128, 64]],
		"dropout_rate": [0.2, 0.5]
	}
}
```

This grid requests eight Experiments with a dense base config. Each inner
`hidden_layers` list is one candidate value, rather than separate dimensions.
Other list-valued fields use the same format:

```json
{
	"exclude_columns": [[], ["race_id"]],
	"tags": [["f1", "pit_strategy"], ["f1", "dense"]]
}
```

This grid requests four Experiments. A candidate can be an empty list if the
field permits it. An empty dimension such as `"tags": []` is rejected.

## Validation rules

- One Sweep uses one architecture. `model.type` belongs in the base config and
  cannot appear in the grid, even with one candidate.
- Unknown fields are rejected in all supplied training configuration, including
  the base config, nested model objects, and the grid.
- JSON objects cannot repeat a field name. Repeated candidate values remain
  separate Experiments, in the supplied order.
- Epochs, batch sizes, and layer sizes must be positive integers. Learning rates
  must be finite and positive. Both split fractions must be greater than zero,
  and their sum must be less than one.
- Activation names must resolve through Keras. Random seeds must be integers
  between 0 and 4294967295, inclusive.
- The base config and every requested combination validate before any
  Experiment starts. Any invalid field, candidate, or combination rejects the
  entire request.
- `{}` requests one Experiment with the exact base config.
- Empty nested objects, such as `{"model": {}}`, make no changes and add no
  dimensions. This example also requests one exact base config.
- Tags and description retain their supplied values unless the grid explicitly
  varies them. A Sweep does not append tags or rewrite descriptions.

## Outcomes and exit codes

If an Experiment fails at runtime, the Sweep continues with the remaining
Experiments. The CLI prints every outcome, including failures, and reports the
requested, succeeded, and failed counts.

Each outcome from `Sweep.run()` also carries cumulative `succeeded` and `failed`
counts. These count attempted Experiments, including failures before a Training
Run opens.

An invalid request exits with code 1 before any Experiment runs. A completed
Sweep exits with code 1 if any Experiment failed, or 0 if all succeeded.

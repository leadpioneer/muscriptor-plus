"""Sampling utilities for autoregressive generation."""

import torch


def length_to_mask(lengths: torch.Tensor, max_len: int | None = None) -> torch.Tensor:
    """Convert a tensor of sequence lengths to a boolean mask."""
    assert len(lengths.shape) == 1
    final_length = int(lengths.max().item()) if not max_len else max_len
    final_length = max(final_length, 1)
    return torch.arange(final_length, device=lengths.device)[None, :] < lengths[:, None]


def multinomial(
    input: torch.Tensor, num_samples: int, replacement: bool = False, *, generator=None
) -> torch.Tensor:
    """torch.multinomial with arbitrary number of dimensions."""
    input_ = input.reshape(-1, input.shape[-1])
    output_ = torch.multinomial(
        input_, num_samples=num_samples, replacement=replacement, generator=generator
    )
    output = output_.reshape(*list(input.shape[:-1]), -1)
    return output


def sample_top_k(probs: torch.Tensor, k: int, num_samples: int = 1) -> torch.Tensor:
    """Sample from top-k probabilities."""
    top_k_value, _ = torch.topk(probs, k, dim=-1)
    min_value_top_k = top_k_value[..., [-1]]
    probs = probs * (probs >= min_value_top_k).float()
    probs = probs / probs.sum(dim=-1, keepdim=True)
    return multinomial(probs, num_samples=num_samples)


def sample_top_p(probs: torch.Tensor, p: float, num_samples: int = 1) -> torch.Tensor:
    """Sample from nucleus (top-p) distribution."""
    probs_sort, probs_idx = torch.sort(probs, dim=-1, descending=True)
    probs_sum = torch.cumsum(probs_sort, dim=-1)
    mask = probs_sum - probs_sort > p
    probs_sort = probs_sort * (~mask).float()
    probs_sort = probs_sort / probs_sort.sum(dim=-1, keepdim=True)
    next_token = multinomial(probs_sort, num_samples=num_samples)
    return torch.gather(probs_idx, -1, next_token)


def sample_from_probs(
    probs: torch.Tensor, top_p: float = 0.0, top_k: int = 0
) -> torch.Tensor:
    """Sample one token from probs, optionally filtered by top-p or top-k."""
    if top_p > 0.0:
        return sample_top_p(probs, top_p)
    if top_k > 0:
        return sample_top_k(probs, top_k)
    return multinomial(probs, num_samples=1)

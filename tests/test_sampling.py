"""Tests for muscriptor/utils/sampling.py."""

import torch

from muscriptor.utils.sampling import (
    length_to_mask,
    multinomial,
    sample_top_k,
    sample_top_p,
)


def test_length_to_mask_basic():
    lengths = torch.tensor([2, 3, 1])
    mask = length_to_mask(lengths)
    assert mask.shape == (3, 3)
    expected = torch.tensor(
        [
            [True, True, False],
            [True, True, True],
            [True, False, False],
        ]
    )
    assert torch.equal(mask, expected)


def test_length_to_mask_explicit_max_len():
    lengths = torch.tensor([1, 2])
    mask = length_to_mask(lengths, max_len=4)
    assert mask.shape == (2, 4)
    assert mask[0].sum() == 1
    assert mask[1].sum() == 2


def test_length_to_mask_all_zero():
    lengths = torch.tensor([0, 0])
    mask = length_to_mask(lengths)
    assert mask.shape == (2, 1)
    assert not mask.any()


def test_multinomial_shape_1d():
    probs = torch.softmax(torch.randn(10), dim=-1)
    out = multinomial(probs, num_samples=3, replacement=True)
    assert out.shape == (3,)


def test_multinomial_shape_batched():
    probs = torch.softmax(torch.randn(4, 10), dim=-1)
    out = multinomial(probs, num_samples=1, replacement=True)
    assert out.shape == (4, 1)


def test_sample_top_k_only_top_tokens():
    # Concentrate mass on tokens 0-4; tokens 5-9 have zero probability.
    probs = torch.zeros(1, 10)
    probs[0, :5] = 0.2
    # num_samples must be <= vocab size without replacement; sample 5 times repeatedly
    results = torch.cat(
        [sample_top_k(probs, k=5, num_samples=1) for _ in range(30)], dim=-1
    )
    assert (results < 5).all(), "top-k should never sample outside the top-k"


def test_sample_top_k_shape():
    probs = torch.softmax(torch.randn(3, 20), dim=-1)
    out = sample_top_k(probs, k=5, num_samples=1)
    assert out.shape == (3, 1)


def test_sample_top_p_shape():
    probs = torch.softmax(torch.randn(2, 15), dim=-1)
    out = sample_top_p(probs, p=0.9, num_samples=1)
    assert out.shape == (2, 1)


def test_sample_top_p_within_vocab():
    probs = torch.softmax(torch.randn(1, 20), dim=-1)
    out = sample_top_p(probs, p=0.95, num_samples=10)
    assert (out >= 0).all() and (out < 20).all()

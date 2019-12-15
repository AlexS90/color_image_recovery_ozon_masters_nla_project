# ================================

import numpy as np
import scipy.linalg as splin


# ================================
# Quaternion algebra
# ================================


def conjugate(Q: np.array) -> np.array:
    """
    Returns conjugate quaternion matrix represented as NumPy tensor of shape (*, *, 4).

    Parameters:
    ----------------
    Q: np.array
        tensor of shape (N, M, 4) representing quaternion matrix

    Returns:
    ----------------
    res: np.array
        tensor of shape (N, M, 4) representing quaternion matrix with imaginary part flipped

    Raises:
    ----------------
    ValueError:
        if tensor last axis has dimension different from 4
    """

    if Q.shape[2] != 4:
        raise ValueError("Wrong tensor shape")
    else:
        return np.concatenate([
            Q[:, :, :1], -Q[:, :, 1:]
        ], axis=2)


def frobenius_norm(Q: np.array) -> np.float64:
    """
    Returns Frobenius norm of quaternion matrix represented as NumPy tensor of shape (*, *, 4).

    Parameters:
    ----------------
    Q: np.array
        tensor of shape (N, M, 4) representing quaternion matrix

    Returns:
    ----------------
    res: np.float64
        Frobenius norm of supplied matrix

    Raises:
    ----------------
    ValueError:
        if tensor last axis has dimension different from 4
    """

    if Q.shape[2] != 4:
        raise ValueError("Wrong tensor shape")
    else:
        return np.sqrt(np.power(Q, 2).sum())


def qdot(Q1: np.array, Q2: np.array) -> np.array:
    """
    Performs multiplication of quaternion matrices represented as NumPy tensor of shape (*, *, 4).
    NOTE: VERY SLOW. FOR TESTING PURPOSES ONLY.

    Parameters:
    ----------------
    Q1, Q2: np.array
        3-dimensional tensors of shapes (N, M, 4), (M, K, 4) representing quaternion matrices

    Returns:
    ----------------
    res: np.array
        3-dimensional tensor of shape (N, K, 4) representing product of quaternion matrices

    Raises:
    ----------------
    ValueError:
        if tensors shapes are mismatched (Q1.shape[1] != Q2.shape[0]) or last axis has dimension different from 4

    """

    if (Q1.shape[2] != 4 or Q2.shape[2] != 4) or (Q1.shape[1] != Q2.shape[0]):
        raise ValueError("Wrong tensor shape or shapes mismatch")
    else:
        return np.stack([
            np.einsum("isk, sjk -> ij", Q1, Q2*np.array([1, -1, -1, -1])[None, None, :]),
            np.einsum("isk, sjk -> ij", Q1, Q2[:, :, (1, 0, 3, 2)]*np.array([1, 1, 1, -1])[None, None, :]),
            np.einsum("isk, sjk -> ij", Q1, Q2[:, :, (2, 3, 0, 1)]*np.array([1, -1, 1, 1])[None, None, :]),
            np.einsum("isk, sjk -> ij", Q1, Q2[:, :, (3, 2, 1, 0)]*np.array([1, 1, -1, 1])[None, None, :])
        ], axis=2)


# ================================
# Matrix transformations
# ================================


def qm2cm(Q: np.array, mask: np.array = None) -> np.array:
    """
    Transforms quaternion matrix represented as NumPy tensor of shape (N, M, 4)
    to complex-valued matrix of shape (2N, 2M)
    based on mapping Q = Qa + Qb*j -> [[Qa, Qb], [-Qb*, Qa*]]

    Parameters:
    ----------------
    Q: np.array
        tensor of shape (N, M, 4) representing quaternion matrix

    Returns:
    ----------------
    res: np.array
        Corresponding 2-dimensional array of shape (2N, 2M) with complex elements

    Raises:
    ----------------
    ValueError:
        if tensor last axis has dimension different from 4
    """

    if Q.shape[2] != 4:
        raise ValueError("Wrong tensor shape or shapes mismatch")
    else:
        Qa = Q[:, :, 0] + 1j * Q[:, :, 1]
        Qb = Q[:, :, 2] + 1j * Q[:, :, 3]

        C = np.vstack([
            np.hstack([Qa, Qb]),
            np.hstack([-np.conj(Qb), np.conj(Qa)])
        ])

        if mask is None:
            C_mask = None
        else:
            C_mask = np.tile(mask, (2, 2))

        return C, C_mask


def cm2qm(C: np.array) -> np.array:
    """
    Transforms complex-valued matrix of shape (2N, 2M)
    to quaternion matrix represented as NumPy tensor of shape (N, M, 4)
    based on mapping Q = Qa + Qb*j -> [[Qa, Qb], [-Qb*, Qa*]]

    Parameters:
    ----------------
    C: np.array
        complex-valued matrix of shape (2N, 2M) to transform

    Returns:
    ----------------
    res: np.array
        Corresponding 3-dimensional tensor of shape (N, M, 4) with real elements

    Raises:
    ----------------
    ValueError:
        if any of array axes has odd dimension
    """

    if (C.shape[0] % 2) or (C.shape[1] % 2):
        raise ValueError("Supplied matrix has odd shape")
    else:
        Qa = C[:C.shape[0] // 2, :C.shape[1] // 2]
        Qb = C[:C.shape[0] // 2, C.shape[1] // 2:]

        return np.stack([
            np.real(Qa), np.imag(Qa), np.real(Qb), np.imag(Qb)
        ], axis=2)


# ================================
# Matrix recovery
# ================================


def lrqmc(qmat, mask, init_rank=None, reg_coef=1e-3, max_iter=100, progress=0, rel_tol=1e-3,
          rot=10.0, rank_mult=0.9, return_norms=False, random_state=None):
    """
    LRQMC method of restoring color image with some of pixels missing

    Parameters:
    ----------------
    qmat: np.array
        Image to be restored, represented as 3-tensor of shape (N, M, 4).
        Color channels are: 1 - red, 2 - blue, 3 - green
    mask: np.array
        Boolean mask of shape (N, M) signaling missing pixels.
        Entries with False correspond to missing values
    init_rank: int
        Initial estimation of low-rank approximation. Must be in [2, min(N, M)]
    reg_coef: float > 0.0
        Regularization coefficient
    max_iter: int
        Maximum allowable number of iterations.
        If required tolerance not achieved after max_iter iterations - computations end
    progress: int > 0
        Controls how often to print output info.
        If zero - no info is printed, if n - info is printed every nth iteration
    rel_tol: float > 0.0
        Convergence tolerance.
        When norm(X[i + 1] - X[i])/X[i] < rel_tol - convergence is achieved (X is restored image)
    rot: float > 0.0
        Rank Overestimation Threshold.
        Controls when to reduce rank estimation. Rank is reduced when eigv[max]*(rank - 1)/sum(eigv) > rot,
        where eigv - eigenvalues of UU^H, rank - current estimation of rank
    rank_mult: float in (0.0, 1.0)
        Rank Multiplier.
        When Rank Overestimation Threshold is exceeded, rank estimation is multiplied by this number
    return_norms: bool
        If True, function returns norms sequence as well.
    random_state: int
        NumPy random generator seed

    Returns:
    ----------------

    Q: np.array
        Restored image, represented as 3-tensor of shape (N, M, 4).
    U, V: np.arrays
        Multiplicants of Q: C(Q) = UV, where C is transformation from quaternion matrix to complex matrix
    norms: list of floats
        Sequence of norms of restored images per iteration
    """

    X, mask_c = qm2cm(qmat, mask)
    X0 = X.copy()

    if (not init_rank) or (init_rank > min(qmat.shape[:2])):
        c_rank = min(qmat.shape[:2])
    else:
        c_rank = init_rank

    np.random.seed(random_state)
    U = np.random.uniform(size=(2*qmat.shape[0], c_rank)) + 1j*np.random.uniform(size=(2*qmat.shape[0], c_rank))
    V = np.random.uniform(size=(c_rank, 2*qmat.shape[1])) + 1j*np.random.uniform(size=(c_rank, 2*qmat.shape[1]))

    norms = np.zeros(max_iter + 1, dtype=np.float64)
    norms[0] = np.linalg.norm(X - U.dot(V))

    flag = True
    ix = 0

    while flag:
        U = (X.dot(np.conj(V.T))).dot(splin.pinv(V.dot(np.conj(V.T)) + reg_coef*np.eye(c_rank), return_rank=False))
        V = splin.pinv(np.conj(U.T).dot(U) + reg_coef*np.eye(c_rank), return_rank=False).dot(np.conj(U.T).dot(X))
        X = X0.copy()
        X[~mask_c] += (U.dot(V))[~mask_c]

        eigvs = np.sort(splin.eigvalsh(np.conj(U.T).dot(U)))[::-1]
        quots = eigvs[:-1]/eigvs[1:]
        max_ind = np.argmax(quots)
        mu = (c_rank - 1)*eigvs[max_ind]/(eigvs.sum() - eigvs[max_ind])

        if mu > rot:
            c_rank = max(max_ind + 2, int(c_rank*rank_mult))
            U = U[:, :c_rank]
            V = V[:c_rank, :]

        norms[ix + 1] = np.linalg.norm(X - U.dot(V))

        if progress and (ix + 1) % progress == 0:
            print(f"Iteration {ix + 1}. "
                  f"Norm reduction: {abs(norms[(ix + 1)] - norms[ix])/norms[ix]*100:.3f} %. "
                  f"Rank / overestimation: {c_rank} / {mu:.2f}")

        if abs(norms[(ix + 1)] - norms[ix])/norms[ix] < rel_tol:
            if progress:
                print(f"Required relative tolerance achieved")

            flag = False
        elif ix >= max_iter:
            if progress:
                print(f"Max iterations count achieved.")

            flag = False
        else:
            ix += 1

    if return_norms:
        return cm2qm(X), U, V, norms
    else:
        return cm2qm(X), U, V

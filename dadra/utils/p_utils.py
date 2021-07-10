import cvxpy as cp
import math
import numpy as np

from functools import partial
from scipy.optimize import minimize_scalar
from tqdm.auto import tqdm


def p_num_samples(epsilon, delta, n_x=3, const=None):
    """Compute the number of samples needed to satisfy the specified probabilistic guarantees for the p-norm ball reachable set estimate

    :param epsilon: The accuracy parameter
    :type epsilon: float
    :param delta: The confidence parameter
    :type delta: float
    :param n_x: The state dimension, defaults to 3
    :type n_x: int
    :param const: The constraints placed on the parameters A and b, defaults to None
    :type const: string, optional
    :return: The number of samples needed to satisfy the specified probabilistic guarantees
    :rtype: int
    """
    if const is None:
        n_theta = 0.5 * (n_x ** 2 + 3 * n_x)
    elif const == "diagonal":
        n_theta = 2 * n_x
    elif const == "scalar":
        n_theta = 1
    N = math.ceil(math.e * (math.log(1 / delta) + n_theta) / (epsilon * (math.e - 1)))
    return N


def solve_p_norm(sample, n_x=3, p=2, const=None):
    """Solves the scenario relaxation problem for the given sample with p-Norm Balls

    :param sample: Sample from dynamical system (num_samples, n_x)
    :type sample: numpy.ndarray
    :param n_x: The state dimension, defaults to 3
    :type n_x: int, optional
    :param p: The order of p-norm, defaults to 2
    :type p: int, optional
    :param const: The constraints placed on the parameters A and b, defaults to None
    :type const: string, optional
    :return: The values of matrix A and vector b corresponding to the optimal p-Norm Ball, as well as the status of the optimizer.
    :rtype: tuple
    """
    if const is None:
        A = cp.Variable((n_x, n_x), symmetric=True)
        b = cp.Variable((n_x, 1))
    elif const == "diagonal":
        a = cp.Variable((n_x, 1))
        A = cp.diag(a)
        b = cp.Variable((n_x, 1))
    elif const == "scalar":
        sigma = cp.Variable()
        A = sigma * np.identity(n_x)
        b = np.zeros((n_x, 1))

    obj = cp.Minimize(-cp.log_det(A))
    constraints = [cp.pnorm(A @ r.reshape(n_x, 1) - b, p=p) <= 1 for r in sample]
    prob = cp.Problem(obj, constraints)
    prob.solve()

    if const != "scalar":
        return A.value, b.value, prob.status
    else:
        return A, b, prob.status


def multi_p_norm(samples, p=2, const=None):
    """Computes a the p-norm ball reachable set estimates across a series of timesteps

    :param samples: The samples from a dynamic system across time, an array of shape (num_samples, timesteps, state_dim)
    :type samples: numpy.ndarray
    :param p: The order of p-norm, defaults to 2
    :type p: int, optional
    :param const: The constraints placed on the parameters A and b, defaults to None
    :type const: string, optional
    :raises ValueError: [description]
    :return: [description]
    :rtype: [type]
    """
    if len(samples.shape) != 3:
        raise ValueError("Samples must be of shape (num_samples, timesteps, state_dim")
    n_x = samples.shape[2]
    keys = ("A", "b", "status")
    solutions = [
        dict(zip(keys, solve_p_norm(sample, n_x, p, const)))
        for sample in tqdm(samples.swapaxes(0, 1))
    ]

    return solutions


def p_norm_cont(arr, axis, default_val, n_x, A_val, b_val, p, minimum=True):
    """Solve for the optimal value that satisfies the p-Norm Ball conditions at the specified axis

    :param arr: Array of shape (n_x - 1,) containing the independent variables of the p-norm condition
    :type arr: numpy.ndarray
    :param axis: The axis of the dependent variable for which to solve for (i.e. z -> axis=2).
    :type axis: int
    :param default_val: The value to return if no solution for the dependent variable is found that satisfies the p-norm conditions
    :type default_val: float
    :param n_x: The state dimension
    :type n_x: int
    :param A_val: The matrix of shape (n_x, n_x) corresponding to the optimal p-norm ball
    :type A_val: numpy.ndarray
    :param b_val: The vector of shape (n_x, 1) corresponding to the optimal p-norm ball
    :type b_val: numpy.ndarray
    :param p: The order of p-norm
    :type p: int
    :param minimum: True if optimizing for the minimal value of the dependent variable that satisfies the p-norm conditions, defaults to True
    :type minimum: bool, optional
    :return: The value at the specified axis which corresponds the the optimal value of the (n_x, 1) vector that satisfies the p-Norm Ball conditions at the specified axis
    :rtype: float
    """
    vec = cp.Variable((n_x, 1))
    other_dims = list(range(n_x))
    other_dims.remove(axis)
    constraints = [vec[i][0] == arr[j] for i, j in zip(other_dims, range(n_x - 1))]
    constraints.append(cp.pnorm(A_val @ vec - b_val, p=p) <= 1)
    if minimum:
        obj = cp.Minimize(vec[axis])
    else:
        obj = cp.Maximize(vec[axis])
    prob = cp.Problem(obj, constraints)

    try:
        prob.solve()
    except:
        return default_val

    if prob.status != "optimal":
        return default_val

    return vec.value[axis]


def p_norm_cont_proj(arr, axis, default_val, n_x, A_val, b_val, p):
    """Minimizes the p-Norm value with respect to value at the specified axis.

    :param arr: Array of shape (n_x - 1,) containing the independent variables of the p-norm condition.
    :type arr: numpy.ndarray
    :param axis: The axis of the dependent variable for which to solve for (i.e. z -> axis=2).
    :type axis: int
    :param default_val: The value to return if no solution for the dependent variable is found that satisfies the p-norm conditions.
    :type default_val: float
    :param n_x: The state dimension.
    :type n_x: int
    :param A_val: The matrix of shape (n_x, n_x) corresponding to the optimal p-norm ball.
    :type A_val: numpy.ndarray
    :param b_val: The vector of shape (n_x, 1) corresponding to the optimal p-norm ball.
    :type b_val: numpy.ndarray
    :param p: The order of p-norm.
    :type p: int
    :return: The value at the specified axis which corresponds the the minimum p-Norm value of the (n_x, 1)  vector.
    :rtype: float
    """
    vec = np.zeros((n_x))
    other_dims = list(range(n_x))
    other_dims.remove(axis)
    for i, j in zip(other_dims, range(n_x - 1)):
        vec[i] = arr[j]

    def f(x):
        vec[axis] = x
        return np.linalg.norm(A_val @ vec.reshape((n_x, 1)) - b_val, ord=p)

    res = minimize_scalar(f)
    vec[axis] = res.x

    if np.linalg.norm(A_val @ vec.reshape((n_x, 1)) - b_val, ord=p) <= 1:
        return res.x
    else:
        return default_val


def p_compute_contour_2D(sample, A_val, b_val, cont_axis=2, n_x=3, p=2, grid_n=200):
    """Computes the 3D contour for 2 dimensions based on sample data and the A_val, and b_val corresponding to the optimal p-norm ball.

    :param sample: Sample from dynamical system (num_samples, n_x)
    :type sample: numpy.ndarray
    :param A_val: The matrix of shape (n_x, n_x) corresponding to the optimal p-norm ball
    :type A_val: numpy.ndarray
    :param b_val: The vector of shape (n_x, 1) corresponding to the optimal p-norm ball
    :type b_val: numpy.ndarray
    :param cont_axis: The axis for which the contours are to be solved for, defaults to 2
    :type cont_axis: int, optional
    :param n_x: The state dimension, defaults to 3
    :type n_x: int, optional
    :param p: The order of p-norm, defaults to 2
    :type p: int, optional
    :param grid_n: The side length of the cube of points to be used for computing contours, defaults to 200
    :type grid_n: int, optional
    :return: The meshgrid, corresponding computed contour, and the extremum values for the chosen axis
    :rtype: tuple
    """
    x_min, x_max = sample[:, 0].min(), sample[:, 0].max()
    y_min, y_max = sample[:, 1].min(), sample[:, 1].max()
    z_min, z_max = sample[:, 2].min(), sample[:, 2].max()

    x = np.linspace(
        x_min - 0.4 * (x_max - x_min), x_max + 0.4 * (x_max - x_min), grid_n
    )
    y = np.linspace(
        y_min - 0.4 * (y_max - y_min), y_max + 0.4 * (y_max - y_min), grid_n
    )
    z = np.linspace(
        x_min - 0.4 * (z_max - z_min), z_max + 0.4 * (z_max - z_min), grid_n
    )

    if cont_axis == 2:
        d0, d1 = np.meshgrid(x, y)
        c_min, c_max = z_min, z_max
    elif cont_axis == 1:
        d0, d1 = np.meshgrid(x, z)
        c_min, c_max = y_min, y_max
    elif cont_axis == 0:
        d0, d1 = np.meshgrid(y, z)
        c_min, c_max = x_min, x_max

    d2 = np.array([d0.flatten(), d1.flatten()]).T

    solve_cont_d2 = partial(
        p_norm_cont_proj,
        axis=cont_axis,
        default_val=c_max + 1,
        n_x=n_x,
        A_val=A_val,
        b_val=b_val,
        p=p,
    )
    cont = np.fromiter(map(solve_cont_d2, d2), dtype=np.float64).reshape(grid_n, grid_n)

    return d0, d1, cont, c_min, c_max


def p_compute_contour_3D(sample, A_val, b_val, cont_axis=2, n_x=3, p=2, grid_n=200):
    """Computes the 3D contour for 3 dimensions based on sample data and the A_val, and b_val corresponding to the optimal p-norm ball.

    :param sample: Sample from dynamical system (num_samples, n_x)
    :type sample: numpy.ndarray
    :param A_val: The matrix of shape (n_x, n_x) corresponding to the optimal p-norm ball
    :type A_val: numpy.ndarray
    :param b_val: The vector of shape (n_x, 1) corresponding to the optimal p-norm ball
    :type b_val: numpy.ndarray
    :param cont_axis: The axis for which the contours are to be solved for, defaults to 2
    :type cont_axis: int, optional
    :param n_x: The state dimension, defaults to 3
    :type n_x: int, optional
    :param p: The order of p-norm, defaults to 2
    :type p: int, optional
    :param grid_n: The side length of the cube of points to be used for computing contours, defaults to 200
    :type grid_n: int, optional
    :param minimum: True if optimizing for the minimal value of the dependent variable that satisfies the p-norm conditions, defaults to True
    :type minimum: bool, optional
    :return: The meshgrid, corresponding computed contour, and the extremum values for the chosen axis
    :rtype: tuple
    """
    x_min, x_max = sample[:, 0].min(), sample[:, 0].max()
    y_min, y_max = sample[:, 1].min(), sample[:, 1].max()
    z_min, z_max = sample[:, 2].min(), sample[:, 2].max()

    x = np.linspace(
        x_min - 0.4 * (x_max - x_min), x_max + 0.4 * (x_max - x_min), grid_n
    )
    y = np.linspace(
        y_min - 0.4 * (y_max - y_min), y_max + 0.4 * (y_max - y_min), grid_n
    )
    z = np.linspace(
        x_min - 0.4 * (z_max - z_min), z_max + 0.4 * (z_max - z_min), grid_n
    )

    if cont_axis == 2:
        d0, d1 = np.meshgrid(x, y)
        c_min, c_max = z_min, z_max
    elif cont_axis == 1:
        d0, d1 = np.meshgrid(x, z)
        c_min, c_max = y_min, y_max
    elif cont_axis == 0:
        d0, d1 = np.meshgrid(y, z)
        c_min, c_max = x_min, x_max

    d2 = np.array([d0.flatten(), d1.flatten()]).T

    solve_cont_d2_min = partial(
        p_norm_cont,
        axis=cont_axis,
        default_val=c_max + 1,
        n_x=n_x,
        A_val=A_val,
        b_val=b_val,
        p=p,
        minimum=True,
    )

    solve_cont_d2_max = partial(
        p_norm_cont,
        axis=cont_axis,
        default_val=c_min - 1,
        n_x=n_x,
        A_val=A_val,
        b_val=b_val,
        p=p,
        minimum=False,
    )

    cont_min = np.fromiter(map(solve_cont_d2_min, d2), dtype=np.float64).reshape(
        grid_n, grid_n
    )
    cont_max = np.fromiter(map(solve_cont_d2_max, d2), dtype=np.float64).reshape(
        grid_n, grid_n
    )

    return d0, d1, cont_min, cont_max, c_min, c_max


def p_compute_vals(sample, A_val, b_val, p=2, grid_n=200):
    """Computes the values within a p-norm ball in 1 dimension

    :param sample: The sample from a specific time step, an array of shape (num_samples,)
    :type sample: numpy.ndarray
    :param A_val: The matrix of shape (1, 1) corresponding to the optimal p-norm ball
    :type A_val: numpy.ndarray
    :param b_val: The vector of shape (1, 1) corresponding to the optimal p-norm ball
    :type b_val: numpy.ndarray
    :param p: The order of p-norm, defaults to 2
    :type p: int, optional
    :param grid_n: The number of points to test for the p-norm ball estimation at each a given time step, defaults to 200
    :type grid_n: int, optional
    :return: The values within the p-norm ball
    :rtype: list
    """
    # assuming sample is (num_samples,) shaped array
    y_min, y_max = sample.min(), sample.max()
    y = np.linspace(
        y_min - 0.4 * (y_max - y_min), y_max + 0.4 * (y_max - y_min), grid_n
    )

    vals = []
    for v in y:
        if np.linalg.norm(A_val @ np.array([[v]]) - b_val, ord=p) <= 1:
            vals.append(v)
    return vals


def p_emp_estimate(samples, A_val, b_val, n_x=3, p=2):
    """Computes the ratio of samples within the estimated reachable set for the p-norm ball reachable set estimation

    :param samples: Sample from dynamical system (num_samples, n_x)
    :type samples: numpy.ndarray
    :param A_val: The matrix of shape (n_x, n_x) corresponding to the optimal p-norm ball
    :type A_val: numpy.ndarray
    :param b_val: The vector of shape (n_x, 1) corresponding to the optimal p-norm ball
    :type b_val: numpy.ndarray
    :param n_x: The state dimension, defaults to 3
    :type n_x: int, optional
    :param p: The order of p-norm, defaults to 2
    :type p: int, optional
    :return: The ratio of samples within the estimated reachability set
    :rtype: float
    """
    num_samples = samples.shape[0]
    count = 0
    for sample in samples:
        vec = sample.reshape(n_x, 1)
        if np.linalg.norm(A_val @ vec - b_val, ord=p) <= 1:
            count += 1
    return count / num_samples

import numpy as np
import cupy as cp
from cupyx.scipy.ndimage import convolve1d

def deriv_charbonnier_over_x(x, sigma, a):
    y = 2*a*(sigma**2 + x**2)**(a-1)
    return y

def deriv_quadra_over_x(x, sigma):
    y = 2 / (sigma**2)
    #y=2
    return y

def deriv_lorentz_over_x(x, sigma):
    y = 2 / (2 * sigma**2 + x**2)
    # Geman_McGlure
    '''sigma=0.1
    y = (2 *sigma)/ (sigma + x**2)**2'''
    return y

deriv_charbonnier_over_x_vec_cp = cp.vectorize(deriv_charbonnier_over_x)
deriv_quadra_over_x_vec_cp = cp.vectorize(deriv_quadra_over_x)
deriv_lorentz_over_x_vec_cp = cp.vectorize(deriv_lorentz_over_x)

def flow_matrix_base(u, v, du, dv, vector, N, M, lmbda, metric,mask,sigma):
    '''
    This function apply  the product marix vector of optical flow without storing the matrix for the
    smoothness term
    Params:
        u: array 
            horizontal displacement
        v: array 
            vertical displacement
        du: array 
            horizontal increment
        dv: array 
            vertical increment
        vector: array
            a given vector
        N: int 
            Number of rows
        M: int 
            Number of columns
        lmbda: float
            Tikhonov parameter
        metric: string
            The chosen metric
        mask: array
            regularization mask 
        sigma: float   
            parameter of the Lorentzian
    Returns:
        res: array
            The product matrix x vector
    '''

    if metric=='lorentz' and sigma ==None:
        print('Sigma Lorentz parameter must be defined')
    if isinstance(mask,np.ndarray):
        lmbda=mask
        lmbda=lmbda.ravel('F')
    #print('maxmin lmbda', lmbda.max(),lmbda.min())
    npixels = N*M
    u_ = cp.reshape(vector[:npixels], (N, M), 'F')
    v_ = cp.reshape(vector[npixels:2*npixels], (N, M), 'F')
    u0 = cp.zeros((N, M), dtype=np.float32)
    v0 = cp.zeros((N, M), dtype=np.float32)
    for i in range(2):
        u__ = convolve1d(u+du, cp.array([-1, 1, 0]), axis=i, mode='reflect')
        v__ = convolve1d(v+dv, cp.array([-1, 1, 0]), axis=i, mode='reflect')
        if metric == 'quadratique':
            pp_su = deriv_quadra_over_x_vec_cp(u__, 0.001)
            pp_sv = deriv_quadra_over_x_vec_cp(v__, 0.001)
        elif metric == 'charbonnier':
            pp_su = deriv_charbonnier_over_x_vec_cp(u__, 0.001, 0.5)
            pp_sv = deriv_charbonnier_over_x_vec_cp(v__, 0.001, 0.5)
        elif metric == 'lorentz':
            #sigma=0.05
            pp_su = deriv_lorentz_over_x_vec_cp(u__, sigma)
            pp_sv = deriv_lorentz_over_x_vec_cp(v__, sigma)

        PhipU = pp_su * \
            convolve1d(u_, cp.array([-1, 1, 0]), axis=i, mode='reflect')
        PhipV = pp_sv * \
            convolve1d(v_, cp.array([-1, 1, 0]), axis=i, mode='reflect')
        u0 += convolve1d(PhipU, cp.array([0, -1, 1]), axis=i, mode='reflect')
        v0 += convolve1d(PhipV, cp.array([0, -1, 1]), axis=i, mode='reflect')
    res = cp.zeros((2*N*M,), dtype=np.float32)
    res[:npixels] =-lmbda*u0.ravel('F')
    res[npixels:2*npixels] = -lmbda*v0.ravel('F')
    #print('lmbda',lmbda.shape)
    return res

def flow_matrix(u, v, du, dv, vector, N, M, Ix, Iy, It, lmbda, metric,mask,sigma):
    '''
    This function apply  the product marix vector of optical flow without storing the matrix 
    we take into account in this function the data part related to the gray value constancy 
    Params:
        u: array 
            horizontal displacement
        v: array 
            vertical displacement
        du: array 
            horizontal increment
        dv: array 
            vertical increment
        vector: array
            a given vector
        N: int 
            Number of rows
        M: int 
            Number of columns
        Ix: array
            x derivative
        Iy: array
            y derivative
        It: array
            temporal derivative
        lmbda: float
            Tikhonov parameter
        metric: string
            The chosen metric
        mask: array
            regularization mask 
        sigma: float   
            parameter of the Lorentzian
    Returns:
        res: array
            The product matrix x vector
    '''

    if metric=='lorentz' and sigma ==None:
        print('Sigma Lorentz parameter must be defined')
    npixels = N*M
    res = flow_matrix_base(u, v, du, dv, vector, N, M, lmbda, metric,mask,sigma)
    u_ = cp.reshape(vector[:npixels], (N, M), 'F')
    v_ = cp.reshape(vector[npixels:2*npixels], (N, M), 'F')
    if metric == 'quadratique':
        #pp_d =deriv_quadra_over_x_vec_cp(It+Ix*du+Iy*dv, 1)
        pp_d =deriv_quadra_over_x_vec_cp(It+Ix*du+Iy*dv, 0.001)
    elif metric == 'charbonnier':
        pp_d = deriv_charbonnier_over_x_vec_cp(It+Ix*du+Iy*dv, 0.001, 0.5)
        #pp_d = deriv_charbonnier_over_x_vec_cp(It+Ix*du+Iy*dv, 0.001, mask)
    elif metric == 'lorentz':
        #sigma=0.05
        pp_d = deriv_lorentz_over_x_vec_cp(It+Ix*du+Iy*dv, sigma)

    u0 = pp_d*(Ix*Ix*u_+Iy*Ix*v_)
    v0 = pp_d*(Ix*Iy*u_+Iy*Iy*v_)
    res[:npixels] = res[:npixels]+np.reshape(u0, (N*M,), 'F')
    res[npixels:2*npixels] = res[npixels:2*npixels]+np.reshape(v0, (N*M,), 'F')
    return res

def right_hand_term(Ix, Iy, It, u, v, du, dv, lmbda, metric,mask,sigma):
    '''
    This function create the right hand term for the system 
    to be solved for a given metric 
    Params:
        Ix: array
            x derivative
        Iy: array
            y derivative
        It: array
            temporal derivative
        u: array 
            horizontal displacement
        v: array 
            vertical displacement
        du: array 
            horizontal increment
        dv: array 
            vertical increment
        lmbda: float
            Tikhonov parameter
        metric: string
            The chosen metric
        mask: array
            regularization mask 
        sigma: float   
            parameter of the Lorentzian
    Returns:
        res: array
            The product matrix x vector
    '''
    if metric=='lorentz' and sigma ==None:
        #print('Sigma Lorentz parameter must be defined')
        raise ValueError('Sigma Lorentz parameter must be defined')
    N, M = Ix.shape
    npixels = N*M
    vector = cp.zeros((2*npixels,), dtype=np.float32)
    vector[:npixels] = u.ravel('F')
    vector[npixels:2*npixels] = v.ravel('F')
    b = -flow_matrix_base(u, v, du, dv, vector, N, M, lmbda, metric,mask,sigma)
    if metric == 'charbonnier':
        pp_d = deriv_charbonnier_over_x_vec_cp(It+Ix*du+Iy*dv, 0.001, 0.5)
    elif metric == 'quadratique':
        #pp_d = deriv_quadra_over_x_vec_cp(It+Ix*du+Iy*dv, 1)
        pp_d = deriv_quadra_over_x_vec_cp(It+Ix*du+Iy*dv, 0.001)
    elif metric == 'lorentz':
        pp_d = deriv_lorentz_over_x_vec_cp(It+Ix*du+Iy*dv, sigma)
    b[:npixels] = b[:npixels]-cp.reshape(pp_d*It*Ix, (npixels), 'F')
    b[npixels:2*npixels] = b[npixels:2*npixels] - cp.reshape(pp_d*It*Iy, (npixels), 'F')
    return b

def flow_final_right_hand_term(Ix, Iy, It, u, v, du, dv, lmbda, metric, alpha,mask,sigma):
    '''
    This function create the right hand term for the system 
    to be solved
    we take into account in this function the GNC Structure
    Params:  
        Ix: array
            x derivative
        Iy: array
            y derivative
        It: array
            temporal derivative
        u: array 
            horizontal displacement
        v: array 
            vertical displacement
        du: array 
            horizontal increment
        dv: array 
            vertical increment
        lmbda: float
            Tikhonov parameter
        metric: string
            The chosen metric
        alpha: float
            The weight of the quadratic formulation in the GNC process
        mask: array
            regularization mask 
        sigma: float   
            parameter of the Lorentzian
    Returns:
        res: array
            The product matrix x vector
    '''
    if alpha == 1:
        # bn=right_hand_term(Ix,Iy,It,u,v,du,dv,lmbda,metric)
        b = right_hand_term(Ix, Iy, It, u, v, du, dv, lmbda, 'quadratique',mask,None)
    elif alpha == 0:
        b = right_hand_term(Ix, Iy, It, u, v, du, dv, lmbda, metric,mask,sigma)
    else:
        bn = right_hand_term(Ix, Iy, It, u, v, du, dv, lmbda, metric,mask,sigma)
        bq = right_hand_term(Ix, Iy, It, u, v, du, dv, lmbda, 'quadratique',mask,None)
        b = alpha*bq+(1-alpha)*bn

    return b

def flow_matrix_final(u, v, du, dv, vector, N, M, Ix, Iy, It, lmbda, metric, alpha,mask,sigma):
    '''
    This function apply  the product marix vector of optical flow without storing the matrix 
    we take into account in this function the GNC Structure  
    Params:
        u: array 
            horizontal displacement
        v: array 
            vertical displacement
        du: array 
            horizontal increment
        dv: array 
            vertical increment
        vector: array
            a given vector
        N: int 
            Number of rows
        M: int 
            Number of columns
        Ix: array
            x derivative
        Iy: array
            y derivative
        It: array
            temporal derivative
        lmbda: float
            Tikhonov parameter
        metric: string
            The chosen metric
        alpha: float
            The weight of the quadratic formulation in the GNC process
        mask: array
            regularization mask 
        sigma: float   
            parameter of the Lorentzian
    Returns:
        res: array
            The product matrix x vector
    '''
    if alpha == 1:
        res = flow_matrix(u, v, du, dv, vector, N, M, Ix,
                          Iy, It, lmbda, 'quadratique',mask,None)
    elif alpha == 0:
        res = flow_matrix(u, v, du, dv, vector, N, M, Ix, Iy, It, lmbda, metric,mask,sigma)
    else:
        resq = flow_matrix(u, v, du, dv, vector, N, M, Ix,
                           Iy, It, lmbda, 'quadratique',mask,None)
        resc = flow_matrix(u, v, du, dv, vector, N, M, Ix, Iy, It, lmbda, metric,mask,sigma)
        res = alpha*resq+(1-alpha)*resc
    return res
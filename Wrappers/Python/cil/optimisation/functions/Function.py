# -*- coding: utf-8 -*-
#  Copyright 2019 United Kingdom Research and Innovation
#  Copyright 2019 The University of Manchester
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
# Authors:
# CIL Developers, listed at: https://github.com/TomographicImaging/CIL/blob/master/NOTICE.txt

import warnings

from numbers import Number
import numpy as np
from functools import reduce

class Function(object):
    
    """ Abstract class representing a function 
    
        :param L: Lipschitz constant of the gradient of the function F(x), when it is differentiable.
        :type L: number, positive, default None
        :param domain: The domain of the function.

        Lipschitz of the gradient of the function; it is a positive real number, such that |f'(x) - f'(y)| <= L ||x-y||, assuming f: IG --> R

    """
    
    
    def __init__(self, L = None):
        # overrides the type check to allow None as initial value
        self._L = L
        
    def __call__(self,x):
        
        r"""Returns the value of the function F at x: :math:`F(x)`
        
        """        
        
        raise NotImplementedError

    def gradient(self, x, out=None):
        
        r"""Returns the value of the gradient of function F at x, if it is differentiable
        
        .. math:: F'(x)
        
        """
        raise NotImplementedError

    def proximal(self, x, tau, out=None):
        
        r"""Returns the proximal operator of function :math:`\tau F` at x        
        .. math:: \mathrm{prox}_{\tau F}(x) = \underset{z}{\mathrm{argmin}} \frac{1}{2}\|z - x\|^{2} + \tau F(z)
        """
        raise NotImplementedError

    def convex_conjugate(self, x):
        r""" Returns the convex conjugate of function :math:`F` at :math:`x^{*}`,
        
        .. math:: F^{*}(x^{*}) = \underset{x^{*}}{\sup} <x^{*}, x> - F(x)
                
        """
        raise NotImplementedError

    def proximal_conjugate(self, x, tau, out = None):
        
        r"""Returns the proximal operator of the convex conjugate of function :math:`\tau F` at :math:`x^{*}`
        
        .. math:: \mathrm{prox}_{\tau F^{*}}(x^{*}) = \underset{z^{*}}{\mathrm{argmin}} \frac{1}{2}\|z^{*} - x^{*}\|^{2} + \tau F^{*}(z^{*})
        
        Due to Moreau’s identity, we have an analytic formula to compute the proximal operator of the convex conjugate :math:`F^{*}`
        
        .. math:: \mathrm{prox}_{\tau F^{*}}(x) = x - \tau\mathrm{prox}_{\tau^{-1} F}(\tau^{-1}x)
                
        """
        try:
            tmp = x
            x.divide(tau, out = tmp)
        except TypeError:
            tmp = x.divide(tau, dtype=np.float32)

        if out is None:
            val = self.proximal(tmp, 1.0/tau)
        else:            
            self.proximal(tmp, 1.0/tau, out = out)
            val = out
                   
        if id(tmp) == id(x):
            x.multiply(tau, out = x)

        # CIL issue #1078, cannot use axpby
        # val.axpby(-tau, 1.0, x, out=val)
        val.multiply(-tau, out = val)
        val.add(x, out = val)

        if out is None:
            return val



    # Algebra for Function Class
    
        # Add functions
        # Subtract functions
        # Add/Substract with Scalar
        # Multiply with Scalar
    
    def __add__(self, other):
        
        """ Returns the sum of the functions.
        
            Cases: a) the sum of two functions :math:`(F_{1}+F_{2})(x) = F_{1}(x) + F_{2}(x)`
                   b) the sum of a function with a scalar :math:`(F_{1}+scalar)(x) = F_{1}(x) + scalar`

        """
        
        if isinstance(other, Function):
            return SumFunction(self, other)
        elif isinstance(other, (SumScalarFunction, ConstantFunction, Number)):
            return SumScalarFunction(self, other)
        else:
            raise ValueError('Not implemented')   
            
    def __radd__(self, other):
        
        """ Making addition commutative. """
        return self + other 
                          
    def __sub__(self, other):
        """ Returns the subtraction of the functions."""
        return self + (-1) * other    

    def __rmul__(self, scalar):
        """Returns a function multiplied by a scalar."""               
        return ScaledFunction(self, scalar)
    
    def __mul__(self, scalar):
        return self.__rmul__(scalar)
    
   
    def centered_at(self, center):
        """ Returns a translated function, namely if we have a function :math:`F(x)` the center is at the origin.         
            TranslateFunction is :math:`F(x - b)` and the center is at point b."""
            
        if center is None:
            return self
        else:
            return TranslateFunction(self, center)
    
    @property
    def L(self):
        '''Lipschitz of the gradient of function f.
        
        L is positive real number, such that |f'(x) - f'(y)| <= L ||x-y||, assuming f: IG --> R'''
        return self._L
        # return self._L
    @L.setter
    def L(self, value):
        '''Setter for Lipschitz constant'''
        if isinstance(value, (Number,)) and value >= 0:
            self._L = value
        else:
            raise TypeError('The Lipschitz constant is a real positive number')
    
class SumFunction(Function):
    
    r"""SumFunction represents the sum of :math:`n\geq2` functions
    
    .. math:: (F_{1} + F_{2} + ... + F_{n})(\cdot)  = F_{1}(\cdot) + F_{2}(\cdot) + ... + F_{n}(\cdot)

    Parameters
    ----------

    *functions : Functions
                 Functions to set up a :class:`.SumFunction`

    Raises
    ------
    ValueError
            If the number of function is strictly less than 2.


    Examples
    --------
    .. math:: F(x) = \|x\|^{2} + \frac{1}{2}\|x - 1\|^{2}

    >>> from cil.optimisation.functions import L2NormSquared
    >>> from cil.framework import ImageGeometry
    >>> f1 = L2NormSquared()
    >>> f2 = 0.5 * L2NormSquared(b = ig.allocate(1))
    >>> F = SumFunction(f1, f2)

    .. math:: F(x) = \sum_{i=1}^{50} \|x - i\|^{2}

    >>> F = SumFunction(*[L2NormSquared(b=i) for i in range(50)])


    """
    
    def __init__(self, *functions ):
                
        super(SumFunction, self).__init__()        
        if len(functions) < 2:
            raise ValueError('At least 2 functions need to be passed')
        self.functions = functions
        
    @property
    def L(self):
        """Returns the Lipschitz constant for the SumFunction
        
        .. math:: L = \sum_{i} L_{i}

        where :math:`L_{i}` is the Lipschitz constant of the smooth function :math:`F_{i}`.
        
        """
        
        L = 0.
        for f in self.functions:
            if f.L is not None:
                L += f.L
            else:
                L = None
                break
        self._L = L
            
        return self._L

    @L.setter
    def L(self, value):
        # call base class setter
        super(SumFunction, self.__class__).L.fset(self, value )

    @property
    def Lmax(self):

        """Returns the maximum Lipschitz constant for the SumFunction
        
        .. math:: L = \max_{i}\{L_{i}\}

        where :math:`L_{i}` is the Lipschitz constant of the smooth function :math:`F_{i}`.
        
        """

        l = []
        for f in self.functions:
            if f.L is not None:
                l.append(f.L)
            else:
                l = None
                break
        self._Lmax = max(l)

        return self._Lmax


    @Lmax.setter
    def Lmax(self, value):
        # call base class setter
        super(SumFunction, self.__class__).Lmax.fset(self, value )        

    def __call__(self,x):
        r"""Returns the value of the sum of functions at :math:`x`.
        
        .. math:: (F_{1} + F_{2} + ... + F_{n})(x) = F_{1}(x) + F_{2}(x) + ... + F_{n}(x)
                
        """  
        ret = 0.
        for f in self.functions:
            ret += f(x)
        return ret


    def gradient(self, x, out=None):
        
        r"""Returns the value of the sum of the gradient of functions at :math:`x`, if all of them are differentiable.
        
        .. math:: (F'_{1} + F'_{2} + ... + F'_{n})(x) = F'_{1}(x) + F'_{2}(x) + ... + F'_{n}(x)
        
        """
        
        if out is None:            
            for i,f in enumerate(self.functions):
                if i == 0:
                    ret = f.gradient(x)
                else:
                    ret += f.gradient(x)
            return ret
        else:
            for i,f in enumerate(self.functions):
                if i == 0:
                    f.gradient(x, out=out)
                else:
                    out += f.gradient(x)

    def __add__(self, other):
        
        """ Addition for the SumFunction.
        
        *  :code:`SumFunction` + :code:`SumFunction` is a :code:`SumFunction`.
         
        *  :code:`SumFunction` + :code:`Function` is a :code:`SumFunction`.

        """
        
        if isinstance(other, SumFunction):
            functions = list(self.functions) + list(other.functions)
            return SumFunction(*functions)
        elif isinstance(other, Function):
            functions = list(self.functions)
            functions.append(other)
            return SumFunction(*functions)
        else:
            return super(SumFunction, self).__add__(other)


class ScaledFunction(Function):
    
    r""" ScaledFunction represents the scalar multiplication with a Function.
    
    Let a function F then and a scalar :math:`\alpha`.
    
    If :math:`G(x) = \alpha F(x)` then:
    
    1. :math:`G(x) = \alpha  F(x)` ( __call__ method )
    2. :math:`G'(x) = \alpha  F'(x)` ( gradient method ) 
    3. :math:`G^{*}(x^{*}) = \alpha  F^{*}(\frac{x^{*}}{\alpha})` ( convex_conjugate method )   
    4. :math:`\mathrm{prox}_{\tau G}(x) = \mathrm{prox}_{(\tau\alpha) F}(x)` ( proximal method ) 
           
    """
    def __init__(self, function, scalar):
        
        super(ScaledFunction, self).__init__() 
                                                     
        if not isinstance (scalar, Number):
            raise TypeError('expected scalar: got {}'.format(type(scalar)))
        
        self.scalar = scalar
        self.function = function       
    @property
    def L(self):
        if self._L is None:
            if self.function.L is not None:
                self._L = abs(self.scalar) * self.function.L
            else:
                self._L = None
        return self._L
    @L.setter
    def L(self, value):
        # call base class setter
        super(ScaledFunction, self.__class__).L.fset(self, value )

    @property
    def scalar(self):
        return self._scalar
    @scalar.setter
    def scalar(self, value):
        if isinstance(value, (Number, )):
            self._scalar = value
        else:
            raise TypeError('Expecting scalar type as a number type. Got {}'.format(type(value)))
    def __call__(self,x, out=None):
        r"""Returns the value of the scaled function.
        
        .. math:: G(x) = \alpha F(x)
        
        """
        return self.scalar * self.function(x)

    def convex_conjugate(self, x):
        r"""Returns the convex conjugate of the scaled function.
        
        .. math:: G^{*}(x^{*}) = \alpha  F^{*}(\frac{x^{*}}{\alpha})
        
        """
        try:
            x.divide(self.scalar, out = x)
            tmp = x
        except TypeError:
            tmp = x.divide(self.scalar, dtype=np.float32)

        val = self.function.convex_conjugate(tmp)

        if id(tmp) == id(x):
            x.multiply(self.scalar, out = x)

        return  self.scalar * val

    
    def gradient(self, x, out=None):
        r"""Returns the gradient of the scaled function.
        
        .. math:: G'(x) = \alpha  F'(x)
        
        """
        if out is None:            
            return self.scalar * self.function.gradient(x)
        else:
            self.function.gradient(x, out=out)
            out *= self.scalar  

    def proximal(self, x, tau, out=None):
        
        r"""Returns the proximal operator of the scaled function.
        
        .. math:: \mathrm{prox}_{\tau G}(x) = \mathrm{prox}_{(\tau\alpha) F}(x)
        
        """        

        return self.function.proximal(x, tau*self.scalar, out=out)     


    def proximal_conjugate(self, x, tau, out = None):
        r"""This returns the proximal operator for the function at x, tau
        """
        try:
            tmp = x
            x.divide(tau, out = tmp)
        except TypeError:
            tmp = x.divide(tau, dtype=np.float32)

        if out is None:
            val = self.function.proximal(tmp, self.scalar/tau )
        else:
            self.function.proximal(tmp, self.scalar/tau, out = out)
            val = out     

        if id(tmp) == id(x):
            x.multiply(tau, out = x)

        # CIL issue #1078, cannot use axpby
        #val.axpby(-tau, 1.0, x, out=val)
        val.multiply(-tau, out = val)
        val.add(x, out = val)

        if out is None:
            return val

class SumScalarFunction(SumFunction):
          
    """ SumScalarFunction represents the sum a function with a scalar. 
    
        .. math:: (F + scalar)(x)  = F(x) + scalar
    
        Although SumFunction has no general expressions for 
        
        i) convex_conjugate
        ii) proximal
        iii) proximal_conjugate
            
        if the second argument is a ConstantFunction then we can derive the above analytically.
    
    """    
    
    def __init__(self, function, constant):
        
        super(SumScalarFunction, self).__init__(function, ConstantFunction(constant))        
        self.constant = constant
        self.function = function
        
    def convex_conjugate(self,x):
        
        r""" Returns the convex conjugate of a :math:`(F+scalar)`
                
        .. math:: (F+scalar)^{*}(x^{*}) = F^{*}(x^{*}) - scalar
                        
        """        
        return self.function.convex_conjugate(x) - self.constant
    
    def proximal(self, x, tau, out=None):
        
        """ Returns the proximal operator of :math:`F+scalar`

        .. math:: \mathrm{prox}_{\tau (F+scalar)}(x) = \mathrm{prox}_{\tau F}
                        
        """                
        return self.function.proximal(x, tau, out=out)        
    
    @property
    def L(self):
        if self._L is None:
            if self.function.L is not None:
                self._L = self.function.L
            else:
                self._L = None
        return self._L
    @L.setter
    def L(self, value):
        # call base class setter
        super(SumScalarFunction, self.__class__).L.fset(self, value )

class ConstantFunction(Function):
    
            
    r""" ConstantFunction: :math:`F(x) = constant, constant\in\mathbb{R}`         
        
    """
    
    def __init__(self, constant = 0):
        self.constant = constant
        super(ConstantFunction, self).__init__(L=0)
        
        
              
    def __call__(self,x):
        
        """ Returns the value of the function, :math:`F(x) = constant`"""
        return self.constant
        
    def gradient(self, x, out=None):
        
        """ Returns the value of the gradient of the function, :math:`F'(x)=0`"""       
        if out is None:
            return x * 0.
        else:
            out.fill(0)
    
    def convex_conjugate(self, x):
                        
        r""" The convex conjugate of constant function :math:`F(x) = c\in\mathbb{R}` is
        
        .. math:: 
            F(x^{*}) 
            =
            \begin{cases}
                -c, & if x^{*} = 0\\
                \infty, & \mbox{otherwise}
            \end{cases}
                                                          
                    
        However, :math:`x^{*} = 0` only in the limit of iterations, so in fact this can be infinity.
        We do not want to have inf values in the convex conjugate, so we have to penalise this value accordingly.
        The following penalisation is useful in the PDHG algorithm, when we compute primal & dual objectives
        for convergence purposes.
        
        .. math:: F^{*}(x^{*}) = \sum \max\{x^{*}, 0\}
        
        """               
        return x.maximum(0).sum()
                
    def proximal(self, x, tau, out=None):
        
        """Returns the proximal operator of the constant function, which is the same element, i.e.,
        
        .. math:: \mathrm{prox}_{\tau F}(x) = x 
        
        """
        if out is None:
            return x.copy()
        else:
            out.fill(x)
        
    @property
    def constant(self):
        return self._constant
    @constant.setter
    def constant(self, value):
        if not isinstance (value, Number):
            raise TypeError('expected scalar: got {}'.format(type(value)))
        self._constant = value
    @property
    def L(self):
        return 0.
    def __rmul__(self, other):
        '''defines the right multiplication with a number'''
        if not isinstance (other, Number):
            raise NotImplemented
        constant = self.constant * other
        return ConstantFunction(constant)

class ZeroFunction(ConstantFunction):
    
    """ ZeroFunction represents the zero function, :math:`F(x) = 0`        
    """
    
    def __init__(self):
        super(ZeroFunction, self).__init__(constant = 0.) 
        
class TranslateFunction(Function):
    
    r""" TranslateFunction represents the translation of function F with respect to the center b.
    
    Let a function F and consider :math:`G(x) = F(x - center)`. 
    
    Function F is centered at 0, whereas G is centered at point b.
    
    If :math:`G(x) = F(x - b)` then:
    
    1. :math:`G(x) = F(x - b)` ( __call__ method )
    2. :math:`G'(x) = F'(x - b)` ( gradient method ) 
    3. :math:`G^{*}(x^{*}) = F^{*}(x^{*}) + <x^{*}, b >` ( convex_conjugate method )   
    4. :math:`\mathrm{prox}_{\tau G}(x) = \mathrm{prox}_{\tau F}(x - b)  + b` ( proximal method ) 
               
    """
    
    def __init__(self, function, center):
        try:
            L = function.L
        except NotImplementedError as nie:
            L = None
        super(TranslateFunction, self).__init__(L = L) 
                        
        self.function = function
        self.center = center
        
    def __call__(self, x):
        
        r"""Returns the value of the translated function.
        
        .. math:: G(x) = F(x - b)
        
        """        
        try:
            x.subtract(self.center, out = x)
            tmp = x
        except TypeError:
            tmp = x.subtract(self.center, dtype=np.float32)

        val = self.function(tmp)

        if id(tmp) == id(x):
            x.add(self.center, out = x)

        return val

    
    def gradient(self, x, out = None):
        
        r"""Returns the gradient of the translated function.
        
        .. math:: G'(x) =  F'(x - b)
        
        """        
        try:
            x.subtract(self.center, out = x)
            tmp = x
        except TypeError:
            tmp = x.subtract(self.center, dtype=np.float32)

        if out is None:
            val = self.function.gradient(tmp)
        else:                       
            self.function.gradient(tmp, out = out)   

        if id(tmp) == id(x):
            x.add(self.center, out = x)

        if out is None:
            return val

    
    def proximal(self, x, tau, out = None):
        
        r"""Returns the proximal operator of the translated function.
        
        .. math:: \mathrm{prox}_{\tau G}(x) = \mathrm{prox}_{\tau F}(x-b) + b
        
        """        
        try:
            x.subtract(self.center, out = x)
            tmp = x
        except TypeError:
            tmp = x.subtract(self.center, dtype=np.float32)

        if out is None:
            val = self.function.proximal(tmp, tau)
            val.add(self.center, out = val)
        else:                    
            self.function.proximal(tmp, tau, out = out)   
            out.add(self.center, out = out)

        if id(tmp) == id(x):
            x.add(self.center, out = x)

        if out is None:
            return val

    def convex_conjugate(self, x):
        
        r"""Returns the convex conjugate of the translated function.
        
        .. math:: G^{*}(x^{*}) = F^{*}(x^{*}) + <x^{*}, b >
        
        """        
        
        return self.function.convex_conjugate(x) + self.center.dot(x)


if __name__ == "__main__":

    F1 = Function()
    F2 = Function()

    res1 = F1 + F2
    print("sum two function", res1.__class__) # SumFunction
    
    res2 = F1 + 5
    print("sum function and scalar",res2.__class__) # SumScalarFunction
    
    res3 = 5 + F1
    print("sum scalar and function",res3.__class__) # SumScalarFunction

    res4 = F1 + ConstantFunction(5)
    print("sum function and constant",res4.__class__) # SumFunction

    res4 = ConstantFunction(5) + 5
    print("sum constant and function",res4.__class__) # SumScalarFunction

    res4 = ZeroFunction() + 5
    print("sum zero function and function",res4.__class__) # SumScalarFunction 

    res3 = res1 + (F1+F2)
    print(res3.__class__)

    from cil.optimisation.functions import L2NormSquared
    from cil.framework import ImageGeometry
    ig = ImageGeometry(3,4)
    f1 = L2NormSquared()
    f2 = 0.5 * L2NormSquared(b = 1)
    F = SumFunction(f1, f2)
    x = ig.allocate(5)
    F(x)   

    G = SumFunction(*[f1]*4)
    len(G.functions)

    F = SumFunction(*[L2NormSquared(b=ig.allocate(i)) for i in range(10)])
    print(len(F.functions))

    # L = F.L 
    # print(res, L)
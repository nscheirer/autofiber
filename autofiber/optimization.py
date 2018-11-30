import sys
import numpy as np


def calcunitvector(vector):
    """ Returns the unit vector of the vector.  """
    return vector / np.linalg.norm(vector)


def calc2d(obj, points):
    coord_sys = obj.implpart.surfaces[0].inplanemats
    coord_sys = np.transpose(coord_sys, axes=(0, 2, 1))
    points_2d = np.matmul(points, coord_sys)
    return points_2d


def minor(arr, i, j):
    # https://stackoverflow.com/questions/3858213/numpy-routine-for-computing-matrix-minors
    # ith row, jth column removed
    return ((-1) ** (i + j)) * arr[:, np.array(range(i)+range(i+1, arr.shape[1]))[:, np.newaxis],
                               np.array(range(j)+range(j+1, arr.shape[2]))]


def build_checkerboard(w, h):
    # https://stackoverflow.com/questions/2169478/how-to-make-a-checkerboard-in-numpy
    re = np.r_[w * [1, -1]]  # even-numbered rows
    ro = np.r_[w * [-1, 1]]  # odd-numbered rows
    return np.row_stack(h * (re, ro))[:w, :h]


def computeglobalstrain(normalized_2d, fiberpoints, vertexids, stiffness_tensor):
    element_vertices_uv = fiberpoints.reshape(fiberpoints.shape[0]/2, 2)[vertexids]

    centroid_2d = np.sum(normalized_2d, axis=1) / 3
    centroid_uv = np.sum(element_vertices_uv, axis=1) / 3

    rel_uv = np.subtract(element_vertices_uv, centroid_uv[:, np.newaxis])
    rel_2d = np.subtract(normalized_2d, centroid_2d[:, np.newaxis])

    rel_uvw = np.pad(rel_uv, [(0, 0), (0, 0), (0, 1)], "constant", constant_values=1).transpose(0, 2, 1)
    rel_3d = np.pad(rel_2d, [(0, 0), (0, 0), (0, 1)], "constant", constant_values=1).transpose(0, 2, 1)

    areas = np.abs(0.5 * np.linalg.det(rel_uvw))

    F = np.matmul(rel_3d, np.linalg.inv(rel_uvw))[:, :2, :2]

    strain = 0.5 * (np.matmul(F.transpose(0, 2, 1), F) - np.identity(F.shape[1]))

    m = np.array([1.0, 1.0, 0.5])[np.newaxis].T
    strain_vector = np.divide(np.array([[strain[:, 0, 0]], [strain[:, 1, 1]], [strain[:, 0, 1]]]).transpose((2, 0, 1)), m).squeeze()[np.newaxis]

    # http://homepages.engineering.auckland.ac.nz/~pkel015/SolidMechanicsBooks/Part_I/BookSM_Part_I/08_Energy/08_Energy_02_Elastic_Strain_Energy.pdf
    strain_energy_density = 0.5*np.multiply(np.einsum('ei,ei->e', np.einsum('ij,ej->ej', stiffness_tensor, strain_vector), strain_vector), areas)

    total_strain_energy = np.sum(strain_energy_density)

    return total_strain_energy


def computeglobalstrain_grad(normalized_2d, fiberpoints, vertexids, stiffness_tensor):
    element_vertices_uv = fiberpoints.reshape(fiberpoints.shape[0]/2, 2)[vertexids]

    centroid_2d = np.sum(normalized_2d, axis=1) / 3
    centroid_uv = np.sum(element_vertices_uv, axis=1) / 3

    rel_uv = np.subtract(element_vertices_uv, centroid_uv[:, np.newaxis])
    rel_2d = np.subtract(normalized_2d, centroid_2d[:, np.newaxis])

    rel_uvw = np.pad(rel_uv, [(0, 0), (0, 0), (0, 1)], "constant", constant_values=1).transpose(0, 2, 1)
    rel_3d = np.pad(rel_2d, [(0, 0), (0, 0), (0, 1)], "constant", constant_values=1).transpose(0, 2, 1)

    areas = np.abs(0.5 * np.linalg.det(rel_uvw))

    minor_mat = np.zeros(rel_uvw.shape)
    for i in range(0, 3):
        for j in range(0, 3):
            minor_mat[:, i, j] = np.linalg.det(minor(rel_uvw, i, j))

    adj_mat = np.multiply(minor_mat, build_checkerboard(minor_mat.shape[1], minor_mat.shape[2])).transpose(0, 2, 1)

    dareas_duv = np.zeros((rel_uvw.shape[0], 6))
    for j in range(0, 3):
        for i in range(0, 2):
            duvw_duij = np.zeros((rel_uvw.shape[1], rel_uvw.shape[2]))
            duvw_duij[i, j] = 1
            dareas_duv[:, j*2+i] = -0.5 * np.trace(np.matmul(adj_mat, duvw_duij), axis1=1, axis2=2)[0]

    F = np.matmul(rel_3d, np.linalg.inv(rel_uvw))[:, :2, :2]

    strain = 0.5 * (np.matmul(F.transpose(0, 2, 1), F) - np.identity(F.shape[1]))

    m = np.array([1.0, 1.0, 0.5])[np.newaxis].T
    strain_vector = np.divide(np.array([[strain[:, 0, 0]], [strain[:, 1, 1]], [strain[:, 0, 1]]]).transpose((2, 0, 1)), m).squeeze()[np.newaxis]

    # [-128.57142551, -264.28571047,  -15.38461447]
    dE_dstrain = areas*np.einsum('ij,ej->ej', stiffness_tensor, strain_vector)

    dF_duv = np.zeros((F.shape[0], 6, F.shape[1], F.shape[2]))
    for j in range(0, 3):
        for i in range(0, 2):
            duvw_duij = np.zeros((rel_uvw.shape[1], rel_uvw.shape[2]))
            duvw_duij[i, j] = 1.0
            dF_duv[:, j*2+i, :, :] = np.matmul(rel_3d, np.matmul(np.matmul(-1.0*np.linalg.inv(rel_uvw), duvw_duij), np.linalg.inv(rel_uvw)))[:, :2, :2]

    dstrainvector_duv = np.zeros((strain_vector.shape[0], strain_vector.shape[1], 6))
    for i in range(0, 6):
        dstrain_du = 0.5 * (np.matmul(dF_duv[:, i, :, :].transpose(0, 2, 1), F) + np.matmul(F.transpose(0, 2, 1), dF_duv[:, i, :, :]))
        dstrainvector_duv[:, :, i] = np.divide(np.array([[dstrain_du[:, 0, 0]], [dstrain_du[:, 1, 1]], [dstrain_du[:, 0, 1]]]).transpose((2, 0, 1)), m).squeeze()[np.newaxis]

    # [-54.59450421, -23.19835417,  -5.6483529 ,  64.28159267, 60.24285852, -41.08324489]
    dE_du = np.einsum('ei,eij->ej', dE_dstrain, dstrainvector_duv).reshape(dstrainvector_duv.shape[0], 3, 2)

    t1 = 0.5*np.matmul(np.matmul(stiffness_tensor, dstrainvector_duv), dstrainvector_duv.transpose(0, 2, 1))*areas
    t2 = 0.5*np.matmul(strain_vector, np.matmul(stiffness_tensor, dstrainvector_duv))*areas
    t3 = 0.5*np.multiply(np.einsum('ei,ei->e', np.einsum('ij,ej->ej', stiffness_tensor, strain_vector), strain_vector), dareas_duv)
    import pdb
    pdb.set_trace()

    point_strain_grad = np.zeros((fiberpoints.shape[0]/2, 2))
    for i in range(0, vertexids.shape[0]):
        ele_vertices = vertexids[i]
        ele_strain_grad = dE_du[i]

        point_strain_grad[ele_vertices] = point_strain_grad[ele_vertices] + ele_strain_grad
    # print(point_strain_grad)
    # pdb.set_trace()
    return point_strain_grad.flatten()


# def computeglobalstrain(normalized_2d, fiberpoints, vertexids, stiffness_tensor):
#     element_vertices_uv = fiberpoints.reshape(fiberpoints.shape[0]/2, 2)[vertexids]
#
#     centroid_2d = np.sum(normalized_2d, axis=1) / 3
#     centroid_uv = np.sum(element_vertices_uv, axis=1) / 3
#
#     rel_uv = np.subtract(element_vertices_uv, centroid_uv[:, np.newaxis])
#     rel_2d = np.subtract(normalized_2d, centroid_2d[:, np.newaxis]).reshape(element_vertices_uv.shape[0], 6)
#
#     areas = np.abs(0.5 * np.linalg.det(np.pad(rel_uv, [(0, 0), (0, 0), (0, 1)], "constant", constant_values=1).transpose(0, 2, 1)))
#
#     C = np.array([[rel_uv[:, 0, 0], rel_uv[:, 0, 1], np.ones(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0])],
#                   [np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), rel_uv[:, 0, 0], rel_uv[:, 0, 1], np.ones(rel_uv.shape[0])],
#                   [rel_uv[:, 1, 0], rel_uv[:, 1, 1], np.ones(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0])],
#                   [np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), rel_uv[:, 1, 0], rel_uv[:, 1, 1], np.ones(rel_uv.shape[0])],
#                   [rel_uv[:, 2, 0], rel_uv[:, 2, 1], np.ones(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0])],
#                   [np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), rel_uv[:, 2, 0], rel_uv[:, 2, 1], np.ones(rel_uv.shape[0])]]).transpose((2, 0, 1))
#
#     Ci = np.repeat(C[:, np.newaxis, :, :], rel_2d.shape[1], axis=1)
#
#     for i in range(0, rel_2d.shape[1]):
#         Ci[:, i][:, :, i] = rel_2d
#
#     detC = np.linalg.det(C)
#     detCi = np.linalg.det(Ci).T
#
#     b = (detCi/detC).T
#
#     B = np.array([[b[:, 0], b[:, 1], b[:, 2]],
#                   [b[:, 3], b[:, 4], b[:, 5]],
#                   [np.zeros(b.shape[0]), np.zeros(b.shape[0]), np.zeros(b.shape[0])]]).transpose((2, 0, 1))
#
#     deform_mat = B
#     # https://en.wikipedia.org/wiki/Infinitesimal_strain_theory
#     # strain = 0.5 * (np.transpose(deform_mat, (0, 2, 1)) + deform_mat) - np.identity(B.shape[1])
#     # Finite strain theory
#     # https://www.klancek.si/sites/default/files/datoteke/files/derivativeofprincipalstretches.pdf
#     strain = 0.5 * (np.matmul(np.transpose(deform_mat, (0, 2, 1)), deform_mat) - np.identity(B.shape[1]))
#
#     m = np.array([1, 1, 1, 0.5, 0.5, 0.5])[np.newaxis].T
#     strain_vector = np.divide(np.array([[strain[:, 0, 0]], [strain[:, 1, 1]], [strain[:, 2, 2]], [strain[:, 1, 2]], [strain[:, 0, 2]], [strain[:, 0, 1]]]).transpose((2, 0, 1)), m).squeeze()
#
#     # http://homepages.engineering.auckland.ac.nz/~pkel015/SolidMechanicsBooks/Part_I/BookSM_Part_I/08_Energy/08_Energy_02_Elastic_Strain_Energy.pdf
#     stress = np.einsum('ij,ej->ej', stiffness_tensor, strain_vector)
#     strain_energy_density = np.multiply(np.einsum('ei,ei->e', stress, strain_vector), areas)
#
#     sys.stdout.write('Strain Energy: %f J/m                    \r' % (np.sum(strain_energy_density),))
#     sys.stdout.flush()
#     return np.sum(strain_energy_density)
#
#
# def computeglobalstrain_grad(normalized_2d, fiberpoints, vertexids, stiffness_tensor):
#     mask = np.array([[0, 9],
#                      [1, 10],
#                      [12, 21],
#                      [13, 22],
#                      [24, 33],
#                      [25, 34]])
#
#     element_vertices_uv = fiberpoints.reshape(fiberpoints.shape[0]/2, 2)[vertexids]
#
#     centroid_2d = np.sum(normalized_2d, axis=1) / 3
#     centroid_uv = np.sum(element_vertices_uv, axis=1) / 3
#
#     rel_uv = np.subtract(element_vertices_uv, centroid_uv[:, np.newaxis])
#     rel_2d = np.subtract(normalized_2d, centroid_2d[:, np.newaxis]).reshape(element_vertices_uv.shape[0], 6)
#
#     areas = np.abs(0.5 * np.linalg.det(np.pad(rel_uv, [(0, 0), (0, 0), (0, 1)], "constant", constant_values=1).transpose(0, 2, 1)))
#
#     C = np.array([[rel_uv[:, 0, 0], rel_uv[:, 0, 1], np.ones(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0])],
#                   [np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), rel_uv[:, 0, 0], rel_uv[:, 0, 1], np.ones(rel_uv.shape[0])],
#                   [rel_uv[:, 1, 0], rel_uv[:, 1, 1], np.ones(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0])],
#                   [np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), rel_uv[:, 1, 0], rel_uv[:, 1, 1], np.ones(rel_uv.shape[0])],
#                   [rel_uv[:, 2, 0], rel_uv[:, 2, 1], np.ones(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0])],
#                   [np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), np.zeros(rel_uv.shape[0]), rel_uv[:, 2, 0], rel_uv[:, 2, 1], np.ones(rel_uv.shape[0])]]).transpose((2, 0, 1))
#
#     rel_uv = rel_uv.reshape(rel_uv.shape[0], 6)
#
#     db_du = np.empty((rel_2d.shape[0], 6, 6))
#     # Calculate each bi
#     Ci = np.repeat(C[:, np.newaxis, :, :], rel_2d.shape[1], axis=1)
#
#     for i in range(0, rel_2d.shape[1]):
#         Ci[:, i][:, :, i] = rel_2d
#
#     detC = np.linalg.det(C)
#     detCi = np.linalg.det(Ci).T
#
#     b = (detCi/detC).T
#
#     for i in range(0, rel_uv.shape[1]):
#         C_i = Ci[:, i, :, :]
#         # Calculate the derivative of the current bi relative to each cij
#         for j in range(0, rel_uv.shape[1]):
#             cij_indx = mask[j]
#
#             ddetci_dcij = 0
#             ddetc_dcij = 0
#             for k in range(0, cij_indx.shape[0]):
#                 unwrapped = np.asarray(np.unravel_index(cij_indx[k], (C.shape[1], C.shape[2]))).T
#
#                 # d(det(C))/d(c_ij)
#                 if unwrapped[1] != i:
#                     ddetci_dcij += np.linalg.det(minor(C_i, unwrapped[0], unwrapped[1]))
#
#                 # d(det(C))/d(c_ij)
#                 ddetc_dcij += np.linalg.det(minor(C, unwrapped[0], unwrapped[1]))
#
#             # d(b_ij)/d(c_ij)
#             db_du[:, i, j] = (ddetci_dcij * detC - detCi[i, :] * ddetc_dcij)/(detC ** 2)
#
#     db_du = db_du.transpose(0, 2, 1).reshape(db_du.shape[0], 6, 2, 3)
#     db_du = np.pad(db_du, [(0, 0), (0, 0), (0, 1), (0, 0)], "constant", constant_values=0)
#
#     # Calculate dE/dstrain
#     B = np.array([[b[:, 0], b[:, 1], b[:, 2]],
#                   [b[:, 3], b[:, 4], b[:, 5]],
#                   [np.zeros(b.shape[0]), np.zeros(b.shape[0]), np.zeros(b.shape[0])]]).transpose((2, 0, 1))
#
#     deform_mat = B
#     # Infinitesimal theory
#     # strain = 0.5 * (np.transpose(deform_mat, (0, 2, 1)) + deform_mat) - np.identity(B.shape[1])
#     # Finite theory
#     strain = 0.5 * (np.matmul(np.transpose(deform_mat, (0, 2, 1)), deform_mat) - np.identity(B.shape[1]))
#
#     m = np.array([1, 1, 1, 0.5, 0.5, 0.5])[np.newaxis].T
#     strain_vector = np.divide(np.array([[strain[:, 0, 0]], [strain[:, 1, 1]], [strain[:, 2, 2]], [strain[:, 1, 2]], [strain[:, 0, 2]], [strain[:, 0, 1]]]).transpose((2, 0, 1)), m).squeeze()[np.newaxis]
#
#     dE_dstrain = np.multiply(np.einsum('ij,ej->ej', stiffness_tensor, strain_vector), np.repeat(areas[np.newaxis], 6, axis=0).T)
#     # dE_dstrain = np.einsum('ij,ej->ej', stiffness_tensor, strain_vector)
#
#     # Calculate dstrain/du
#     # Infinitesimal
#     # dstrain_du = 0.5 * (np.transpose(db_du, (0, 1, 3, 2)) + db_du)
#     # Finite theory dstrain/du
#     dstrain_du = 0.5 * (np.matmul(np.transpose(db_du, (0, 1, 3, 2)), deform_mat[:, np.newaxis, :, :]) + np.matmul(
#         np.transpose(deform_mat, (0, 2, 1))[:, np.newaxis, :, :], db_du))
#
#     dstrain_vector_du = np.divide(np.array([[dstrain_du[:, :, 0, 0]], [dstrain_du[:, :, 1, 1]], [dstrain_du[:, :, 2, 2]], [dstrain_du[:, :, 1, 2]], [dstrain_du[:, :, 0, 2]], [dstrain_du[:, :, 0, 1]]]).transpose((2, 3, 0, 1)), m).squeeze()[np.newaxis]
#
#     dE_du = np.einsum('eij,ej->ei', dstrain_vector_du, dE_dstrain).reshape(dstrain_vector_du.shape[0], 3, 2)
#
#     point_strain_grad = np.zeros((fiberpoints.shape[0]/2, 2))
#     for i in range(0, vertexids.shape[0]):
#         ele_vertices = vertexids[i]
#         ele_strain_grad = dE_du[i]
#
#         point_strain_grad[ele_vertices] = point_strain_grad[ele_vertices] + ele_strain_grad
#     return point_strain_grad.flatten()


def optimize(f, grad, x_0, eps=1e-7):
    import pdb
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import axes3d

    x = x_0.flatten()
    b = f(x)
    print("Starting Energy: %s" % b)

    its = 10
    strains = np.zeros(its)
    for i in range(0, its):
        cur_grad = grad(x)
        x = x - eps * cur_grad
        b = f(x)

        strains[i] = b
        print("Current Strain Energy: %s" % b)

    fig = plt.figure()
    plt.scatter(x_0[:, 0], x_0[:, 1])
    plt.scatter(x.reshape(x_0.shape)[:, 0], x.reshape(x_0.shape)[:, 1])

    fig = plt.figure()
    plt.plot(range(0, its), strains)

    return x.reshape(x_0.shape)

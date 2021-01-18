import copy
import numpy as np
import modeling.modelcollection as mc
import basis.robotmath as rm
import robotsim._kinematics.jlchain as jl
import robotsim._kinematics.collisionchecker as cc


class GripperInterface(object):

    def __init__(self, pos=np.zeros(3), rotmat=np.eye(3), cdmesh_type='aabb', name='yumi_gripper'):
        self.name = name
        self.pos = pos
        self.rotmat = rotmat
        self.cdmesh_type = cdmesh_type # aabb, convexhull, or triangles
        # joints
        # - coupling - No coupling by default
        self.coupling = jl.JLChain(pos=self.pos, rotmat=self.rotmat, homeconf=np.zeros(0), name='coupling')
        self.coupling.jnts[1]['loc_pos'] = np.array([0, 0, .0])
        self.coupling.lnks[0]['name'] = 'coupling_lnk0'
        # toggle on the following part to assign an explicit mesh model to a coupling
        # self.coupling.lnks[0]['meshfile'] = os.path.join(this_dir, "meshes", "xxx.stl")
        # self.coupling.lnks[0]['rgba'] = [.2, .2, .2, 1]
        self.coupling.reinitialize()
        # jaw center
        self.jaw_center_pos = np.zeros(3)
        self.jaw_center_rotmat = np.eye(3)
        # jaw width
        self.jaw_width_rng = [0.0, 5.0]
        # collision detection
        self.cc = None
        # cd mesh collection for precise collision checking
        self.cdmesh_collection = mc.ModelCollection()
        # is fk updated for lazy update of cdmesh_collection
        self._is_fk_updated = True

    @property
    def is_fk_updated(self):
        return self._is_fk_updated

    def is_collided(self, obstacle_list=[], otherrobot_list=[]):
        """
        Interface for "is cdprimit collided", must be implemented in child class
        :param obstacle_list:
        :param otherrobot_list:
        :return:
        author: weiwei
        date: 20201223
        """
        return_val =  self.cc.is_collided(obstacle_list=obstacle_list, otherrobot_list=otherrobot_list,
                                          need_update=self._is_fk_updated)
        self._is_fk_updated = False
        return return_val

    def is_mesh_collided(self, objcm_list=[], toggle_debug=False):
        for i, cdelement in enumerate(self.cc.all_cdelements):
            pos = cdelement['gl_pos']
            rotmat = cdelement['gl_rotmat']
            self.cdmesh_collection.cm_list[i].set_pos(pos)
            self.cdmesh_collection.cm_list[i].set_rotmat(rotmat)
            iscollided, collided_points = self.cdmesh_collection.cm_list[i].is_mcdwith(objcm_list, True)
            if iscollided:
                if toggle_debug:
                    print(self.cdmesh_collection.cm_list[i].get_homomat())
                    self.cdmesh_collection.cm_list[i].show_cdmesh()
                    for objcm in objcm_list:
                        objcm.show_cdmesh()
                    for point in collided_points:
                        import modeling.geometricmodel as gm
                        gm.gen_sphere(point, radius=.001).attach_to(base)
                    print("collided")
                return True
        return False

    def fix_to(self, pos, rotmat):
        raise NotImplementedError

    def fk(self, motion_val):
        raise NotImplementedError

    def jaw_to(self, jaw_width):
        raise NotImplementedError

    def get_jawwidth(self):
        raise NotImplementedError

    def grip_at(self, gl_jaw_center, gl_hndz, gl_hndx, jaw_width):
        hnd_rotmat = np.eye(3)
        hnd_rotmat[:, 2] = rm.unit_vector(gl_hndz)
        hnd_rotmat[:, 0] = rm.unit_vector(gl_hndx)
        hnd_rotmat[:, 1] = np.cross(hnd_rotmat[:3, 2], hnd_rotmat[:3, 0])
        hnd_pos = gl_jaw_center - hnd_rotmat.dot(self.jaw_center_pos)
        self.fix_to(hnd_pos, hnd_rotmat)
        self.jaw_to(jaw_width)
        return [jaw_width, gl_jaw_center, hnd_pos, hnd_rotmat]

    def show_cdprimit(self):
        self.cc.show_cdprimit(need_update=self._is_fk_updated)
        self._is_fk_updated = False

    def unshow_cdprimit(self):
        self.cc.unshow_cdprimit()

    def show_cdmesh(self):
        if self._is_fk_updated:
            for i, cdelement in enumerate(self.cc.all_cdelements):
                pos = cdelement['gl_pos']
                rotmat = cdelement['gl_rotmat']
                self.cdmesh_collection.cm_list[i].set_pos(pos)
                self.cdmesh_collection.cm_list[i].set_rotmat(rotmat)
            self._is_fk_updated = False
        self.cdmesh_collection.show_cdmesh()

    def unshow_cdmesh(self):
        self.cdmesh_collection.unshow_cdmesh()

    def gen_stickmodel(self,
                       tcp_jntid=None,
                       tcp_loc_pos=None,
                       tcp_loc_rotmat=None,
                       toggle_tcpcs=False,
                       toggle_jntscs=False,
                       toggle_connjnt=False,
                       name='yumi_gripper_stickmodel'):
        raise NotImplementedError

    def gen_meshmodel(self,
                      tcp_jntid=None,
                      tcp_loc_pos=None,
                      tcp_loc_rotmat=None,
                      toggle_tcpcs=False,
                      toggle_jntscs=False,
                      rgba=None,
                      name='yumi_gripper_meshmodel'):
        raise NotImplementedError

    def enable_cc(self):
        self.cc = cc.CollisionChecker("collision_checker")

    def disable_cc(self):
        """
        clear pairs and nodepath
        :return:
        """
        for cdelement in self.cc.all_cdelements:
            cdelement['cdprimit_childid'] = -1
        self.cc = None

    def copy(self):
        self_copy = copy.deepcopy(self)
        # deepcopying colliders are problematic, I have to update it manually
        if self.cc is not None:
            for child in self_copy.cc.np.getChildren():
                self_copy.cc.ctrav.addCollider(child, self_copy.cc.chan)
        return self_copy


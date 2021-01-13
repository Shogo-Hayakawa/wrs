import math
import numpy as np
import basis.robotmath as rm
import warnings as wns


class NIKOptimizer(object):

    def __init__(self, robot, jlc_name, wlnratio=.15):
        self.rbt = robot
        self.jlc_name = jlc_name
        # IK macros
        wt_pos = 0.628  # 0.628m->1 == 0.01->0.00628m
        wt_agl = 1 / (math.pi * math.pi)  # pi->1 == 0.01->0.18degree
        self.ws_wtlist = [wt_pos, wt_pos, wt_pos, wt_agl, wt_agl, wt_agl]
        # maximum reach
        self.max_rng = 2

        # extract min max for quick access
        self.jmvmin = np.zeros(self.rbt.ndof)
        self.jmvmax = np.zeros(self.rbt.ndof)
        counter = 0
        for id in jlobject.tgtjnts:
            self.jmvmin[counter] = jlobject.jnts[id]['motion_rng'][0]
            self.jmvmax[counter] = jlobject.jnts[id]['motion_rng'][1]
            counter += 1
        self.jmvrng = self.jmvmax - self.jmvmin
        self.jmvmin_threshhold = self.jmvmin + self.jmvrng * wlnratio
        self.jmvmax_threshhold = self.jmvmax - self.jmvrng * wlnratio

    def _jacobian_sgl(self, tcp_jntid):
        """
        compute the jacobian matrix of a rjlinstance
        only a single tcp_jntid is acceptable
        :param tcp_jntid: the joint id where the tool center pose is specified, single vlaue
        :return: jmat, a 6xn nparray
        author: weiwei
        date: 20161202, 20200331, 20200706
        """
        jmat = np.zeros((6, len(self.jlobject.tgtjnts)))
        counter = 0
        for jid in self.jlobject.tgtjnts:
            grax = self.jlobject.jnts[jid]["gl_motionax"]
            if self.jlobject.jnts[jid]["type"] == 'revolute':
                diffq = self.jlobject.jnts[tcp_jntid]["gl_posq"] - self.jlobject.jnts[jid]["gl_posq"]
                jmat[:3, counter] = np.cross(grax, diffq)
                jmat[3:6, counter] = grax
            if self.jlobject.jnts[jid]["type"] == 'prismatic':
                jmat[:3, counter] = grax
            counter += 1
            if jid == tcp_jntid:
                break
        return jmat

    def _wln_weightmat(self, jntvalues):
        """
        get the wln weightmat
        :param jntvalues:
        :return:
        author: weiwei
        date: 20201126
        """
        wtmat = np.ones(self.jlobject.ndof)
        # min damping interval
        selection = (jntvalues - self.jmvmin_threshhold < 0)
        diff_selected = self.jmvmin_threshhold[selection] - jntvalues[selection]
        wtmat[selection] = -2 * np.power(diff_selected, 3) + 3 * np.power(diff_selected, 2)
        # max damping interval
        selection = (jntvalues - self.jmvmax_threshhold > 0)
        diff_selected = jntvalues[selection] - self.jmvmax_threshhold[selection]
        wtmat[selection] = -2 * np.power(diff_selected, 3) + 3 * np.power(diff_selected, 2)
        wtmat[jntvalues >= self.jmvmax] = 1e-6
        wtmat[jntvalues <= self.jmvmin] = 1e-6
        return np.diag(wtmat)

    def jacobian(self, tcp_jntid):
        """
        compute the jacobian matrix of a rjlinstance
        multiple tcp_jntid acceptable
        :param tcp_jntid: the joint id where the tool center pose is specified, single vlaue or list
        :return: jmat, a sum(len(option))xn nparray
        author: weiwei
        date: 20161202, 20200331, 20200706, 20201114
        """
        if isinstance(tcp_jntid, list):
            jmat = np.zeros((6 * (len(tcp_jntid)), len(self.jlobject.tgtjnts)))
            for i, this_tcp_jntid in enumerate(tcp_jntid):
                jmat[6 * i:6 * i + 6, :] = self._jacobian_sgl(this_tcp_jntid)
            return jmat
        else:
            return self._jacobian_sgl(tcp_jntid)

    def manipulability(self, tcp_jntid):
        """
        compute the yoshikawa manipulability of the rjlinstance
        :param tcp_jntid: the joint id where the tool center pose is specified, single vlaue or list
        :return:
        author: weiwei
        date: 20200331
        """
        jmat = self.jacobian(tcp_jntid)
        return math.sqrt(np.linalg.det(np.dot(jmat, jmat.transpose())))

    def manipulability_axmat(self, tcp_jntid):
        """
        compute the yasukawa manipulability of the rjlinstance
        :param tcp_jntid: the joint id where the tool center pose is specified, single vlaue or list
        :return: axmat with each column being the manipulability
        """
        armjac = self.jacobian(tcp_jntid)
        jjt = np.dot(armjac, armjac.T)
        pcv, pcaxmat = np.linalg.eig(jjt)
        # only keep translation
        axmat = np.eye(3)
        axmat[:, 0] = np.sqrt(pcv[0]) * pcaxmat[:3, 0]
        axmat[:, 1] = np.sqrt(pcv[1]) * pcaxmat[:3, 1]
        axmat[:, 2] = np.sqrt(pcv[2]) * pcaxmat[:3, 2]
        return axmat

    def get_gl_tcp(self, tcp_jnt_id, tcp_loc_pos, tcp_loc_rotmat):
        """
        Get the global tool center pose given tcp_jntid, tcp_loc_pos, tcp_loc_rotmat
        tcp_jntid, tcp_loc_pos, tcp_loc_rotmat are the tool center pose parameters. They are
        used for temporary computation, the self.tcp_xxx parameters will not be changed
        in case None is provided, the self.tcp_jntid, self.tcp_loc_pos, self.tcp_loc_rotmat will be used
        :param tcp_jnt_id: a joint ID in the self.tgtjnts
        :param tcp_loc_pos: 1x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :param tcp_loc_rotmat: 3x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :return: a single value or a list depending on the input
        author: weiwei
        date: 20200706
        """
        if tcp_jnt_id is None:
            tcp_jnt_id = self.jlobject.tcp_jntid
        if tcp_loc_pos is None:
            tcp_loc_pos = self.jlobject.tcp_loc_pos
        if tcp_loc_rotmat is None:
            tcp_loc_rotmat = self.jlobject.tcp_loc_rotmat
        if isinstance(tcp_jnt_id, list):
            returnposlist = []
            returnrotmatlist = []
            for i, jid in enumerate(tcp_jnt_id):
                tcp_gl_pos = np.dot(self.jlobject.jnts[jid]["gl_rotmatq"], tcp_loc_pos[i]) + \
                                self.jlobject.jnts[jid]["gl_posq"]
                tcp_gl_rotmat = np.dot(self.jlobject.jnts[jid]["gl_rotmatq"], tcp_loc_rotmat[i])
                returnposlist.append(tcp_gl_pos)
                returnrotmatlist.append(tcp_gl_rotmat)
            return [returnposlist, returnrotmatlist]
        else:
            tcp_gl_pos = np.dot(self.jlobject.jnts[tcp_jnt_id]["gl_rotmatq"], tcp_loc_pos) + \
                         self.jlobject.jnts[tcp_jnt_id]["gl_posq"]
            tcp_gl_rotmat = np.dot(self.jlobject.jnts[tcp_jnt_id]["gl_rotmatq"], tcp_loc_rotmat)
            return tcp_gl_pos, tcp_gl_rotmat

    def tcp_error(self, tgt_pos, tgt_rot, tcp_jntid, tcp_loc_pos, tcp_loc_rotmat):
        """
        compute the error between the rjlinstance's end and tgt_pos, tgt_rot
        NOTE: if list, len(tgt_pos)=len(tgt_rot) <= len(tcp_jntid)=len(tcp_loc_pos)=len(tcp_loc_rotmat)
        :param tgt_pos: the position vector of the goal (could be a single value or a list of jntid)
        :param tgt_rot: the rotation matrix of the goal (could be a single value or a list of jntid)
        :param tcp_jntid: a joint ID in the self.tgtjnts
        :param tcp_loc_pos: 1x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :param tcp_loc_rotmat: 3x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :return: a 1x6 nparray where the first three indicates the displacement in pos,
                    the second three indictes the displacement in rot
        author: weiwei
        date: 20180827, 20200331, 20200705
        """
        tcp_globalpos, tcp_globalrotmat = self.get_gl_tcp(tcp_jntid, tcp_loc_pos, tcp_loc_rotmat)
        if isinstance(tgt_pos, list):
            deltapw = np.zeros(6 * len(tgt_pos))
            for i, thistgt_pos in enumerate(tgt_pos):
                deltapw[6 * i:6 * i + 3] = (thistgt_pos - tcp_globalpos[i])
                deltapw[6 * i + 3:6 * i + 6] = rm.deltaw_between_rotmat(tgt_rot[i], tcp_globalrotmat[i].T)
            return deltapw
        else:
            deltapw = np.zeros(6)
            deltapw[0:3] = (tgt_pos - tcp_globalpos)
            deltapw[3:6] = rm.deltaw_between_rotmat(tgt_rot, tcp_globalrotmat.T)
            return deltapw

    def regulate_jnts(self):
        """
        check if the given jntvalues is inside the oeprating range
        The joint values out of range will be pulled back to their maxima
        :return: Two parameters, one is true or false indicating if the joint values are inside the range or not
                The other is the joint values after dragging.
                If the joints were not dragged, the same joint values will be returned
        author: weiwei
        date: 20161205
        """
        counter = 0
        for id in self.jlobject.tgtjnts:
            if self.jlobject.jnts[id]["type"] is 'revolute':
                if self.jlobject.jnts[id]['motion_rng'][1] - self.jlobject.jnts[id]['motion_rng'][0] >= math.pi * 2:
                    rm.regulate_angle(self.jlobject.jnts[id]['motion_rng'][0], self.jlobject.jnts[id]['motion_rng'][1],
                                      self.jlobject.jnts[id]["movement"])
            counter += 1

    def check_jntranges_drag(self, jntvalues):
        """
        check if the given jntvalues is inside the oeprating range
        The joint values out of range will be pulled back to their maxima
        :param jntvalues: a 1xn numpy ndarray
        :return: Two parameters, one is true or false indicating if the joint values are inside the range or not
                The other is the joint values after dragging.
                If the joints were not dragged, the same joint values will be returned
        author: weiwei
        date: 20161205
        """
        counter = 0
        isdragged = np.zeros_like(jntvalues)
        jntvaluesdragged = jntvalues.copy()
        for id in self.jlobject.tgtjnts:
            if self.jlobject.jnts[id]["type"] == 'revolute':
                if self.jlobject.jnts[id]['motion_rng'][1] - self.jlobject.jnts[id]['motion_rng'][0] < math.pi * 2:
                    # if jntvalues[counter] < jlinstance.jnts[id]['motion_rng'][0]:
                    #     isdragged[counter] = 1
                    #     jntvaluesdragged[counter] = jlinstance.jnts[id]['motion_rng'][0]
                    # elif jntvalues[counter] > jlinstance.jnts[id]['motion_rng'][1]:
                    #     isdragged[counter] = 1
                    #     jntvaluesdragged[counter] = jlinstance.jnts[id]['motion_rng'][1]
                    print("Drag revolute")
                    if jntvalues[counter] < self.jlobject.jnts[id]['motion_rng'][0] or jntvalues[counter] > \
                            self.jlobject.jnts[id]['motion_rng'][1]:
                        isdragged[counter] = 1
                        jntvaluesdragged[counter] = (self.jlobject.jnts[id]['motion_rng'][1] + self.jlobject.jnts[id][
                            'motion_rng'][0]) / 2
            elif self.jlobject.jnts[id]["type"] == 'prismatic':  # prismatic
                # if jntvalues[counter] < jlinstance.jnts[id]['motion_rng'][0]:
                #     isdragged[counter] = 1
                #     jntvaluesdragged[counter] = jlinstance.jnts[id]['motion_rng'][0]
                # elif jntvalues[counter] > jlinstance.jnts[id]['motion_rng'][1]:
                #     isdragged[counter] = 1
                #     jntvaluesdragged[counter] = jlinstance.jnts[id]['motion_rng'][1]
                print("Drag prismatic")
                if jntvalues[counter] < self.jlobject.jnts[id]['motion_rng'][0] or jntvalues[counter] > \
                        self.jlobject.jnts[id]['motion_rng'][1]:
                    isdragged[counter] = 1
                    jntvaluesdragged[counter] = (self.jlobject.jnts[id]['motion_rng'][1] + self.jlobject.jnts[id][
                        "rngmin"]) / 2
        return isdragged, jntvaluesdragged

    def num_ik(self,
               tgt_pos,
               tgt_rot,
               start_conf=None,
               tcp_jntid=None,
               tcp_loc_pos=None,
               tcp_loc_rotmat=None,
               local_minima="accept",
               toggle_debug=False):
        """
        solveik numerically using the Levenberg-Marquardt Method
        the details of this method can be found in: https://www.math.ucsd.edu/~sbuss/ResearchWeb/ikmethods/iksurvey.pdf
        NOTE: if list, len(tgt_pos)=len(tgt_rot) <= len(tcp_jntid)=len(tcp_loc_pos)=len(tcp_loc_rotmat)
        :param tgt_pos: the position of the goal, 1-by-3 numpy ndarray
        :param tgt_rot: the orientation of the goal, 3-by-3 numpyndarray
        :param start_conf: the starting configuration used in the numerical iteration
        :param tcp_jntid: a joint ID in the self.tgtjnts
        :param tcp_loc_pos: 1x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :param tcp_loc_rotmat: 3x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :param local_minima: what to do at local minima: "accept", "randomrestart", "end"
        :return: a 1xn numpy ndarray
        author: weiwei
        date: 20180203, 20200328
        """
        deltapos = tgt_pos - self.jlobject.jnts[0]['gl_pos0']
        if np.linalg.norm(deltapos) > self.max_rng:
            wns.WarningMessage("The goal is outside maximum range!")
            return None
        if tcp_jntid is None:
            tcp_jntid = self.jlobject.tcp_jntid
        if tcp_loc_pos is None:
            tcp_loc_pos = self.jlobject.tcp_loc_pos
            print(self.jlobject.tcp_loc_pos)
        if tcp_loc_rotmat is None:
            tcp_loc_rotmat = self.jlobject.tcp_loc_rotmat
        # trim list
        if isinstance(tgt_pos, list):
            tcp_jntid = tcp_jntid[0:len(tgt_pos)]
            tcp_loc_pos = tcp_loc_pos[0:len(tgt_pos)]
            tcp_loc_rotmat = tcp_loc_rotmat[0:len(tgt_pos)]
        elif isinstance(tcp_jntid, list):
            tcp_jntid = tcp_jntid[0]
            tcp_loc_pos = tcp_loc_pos[0]
            tcp_loc_rotmat = tcp_loc_rotmat[0]
        jntvalues_bk = self.jlobject.get_jntvalues()
        jntvalues_iter = self.jlobject.homeconf if start_conf is None else start_conf.copy()
        self.jlobject.fk(jnt_values=jntvalues_iter)
        jntvalues_ref = jntvalues_iter.copy()

        if isinstance(tcp_jntid, list):
            diaglist = []
            for i in tcp_jntid:
                diaglist += self.ws_wtlist
            ws_wtdiagmat = np.diag(diaglist)
        else:
            ws_wtdiagmat = np.diag(self.ws_wtlist)
        # sqrtinv_ws_wtdiagmat = np.linalg.inv(np.diag(np.sqrt(np.diag(ws_wtdiagmat))))

        if toggle_debug:
            if "jlm" not in dir():
                import robotsim._kinematics.jlchainmesh as jlm
            if "plt" not in dir():
                import matplotlib.pyplot as plt
            # jlmgen = jlm.JntLnksMesh()
            dqbefore = []
            dqcorrected = []
            dqnull = []
            ajpath = []
        errnormlast = 0.0
        errnormmax = 0.0
        for i in range(100):
            jmat = self.jacobian(tcp_jntid)
            err = self.tcp_error(tgt_pos, tgt_rot, tcp_jntid, tcp_loc_pos, tcp_loc_rotmat)
            errnorm = err.T.dot(ws_wtdiagmat).dot(err)
            # err = .05 / errnorm * err if errnorm > .05 else err
            if errnorm > errnormmax:
                errnormmax = errnorm
            if toggle_debug:
                print(errnorm)
                ajpath.append(self.jlobject.get_jntvalues())
            if errnorm < 1e-6:
                if toggle_debug:
                    fig = plt.figure()
                    axbefore = fig.add_subplot(411)
                    axbefore.set_title('Original dq')
                    axnull = fig.add_subplot(412)
                    axnull.set_title('dqref on Null space')
                    axcorrec = fig.add_subplot(413)
                    axcorrec.set_title('Minimized dq')
                    axaj = fig.add_subplot(414)
                    axbefore.plot(dqbefore)
                    axnull.plot(dqnull)
                    axcorrec.plot(dqcorrected)
                    axaj.plot(ajpath)
                    plt.show()
                # self.regulate_jnts()
                jntvalues_return = self.jlobject.get_jntvalues()
                self.jlobject.fk(jnt_values=jntvalues_bk)
                return jntvalues_return
            else:
                # judge local minima
                if abs(errnorm - errnormlast) < 1e-12:
                    if toggle_debug:
                        fig = plt.figure()
                        axbefore = fig.add_subplot(411)
                        axbefore.set_title('Original dq')
                        axnull = fig.add_subplot(412)
                        axnull.set_title('dqref on Null space')
                        axcorrec = fig.add_subplot(413)
                        axcorrec.set_title('Minimized dq')
                        axaj = fig.add_subplot(414)
                        axbefore.plot(dqbefore)
                        axnull.plot(dqnull)
                        axcorrec.plot(dqcorrected)
                        axaj.plot(ajpath)
                        plt.show()
                    if local_minima == 'accept':
                        wns.warn(
                            'Bypassing local minima! The return value is a local minima, rather than the exact IK result.')
                        jntvalues_return = self.jlobject.get_jntvalues()
                        self.jlobject.fk(jntvalues_bk)
                        return jntvalues_return
                    elif local_minima == 'randomrestart':
                        wns.warn('Local Minima! Random restart at local minima!')
                        jntvalues_iter = self.jlobject.rand_conf()
                        self.jlobject.fk(jntvalues_iter)
                        continue
                    else:
                        print('No feasible IK solution!')
                        break
                else:
                    # -- notes --
                    ## note1: do not use np.linalg.inv since it is not precise
                    ## note2: use np.linalg.solve if the system is exactly determined, it is faster
                    ## note3: use np.linalg.lstsq if there might be singularity (no regularization)
                    ## see https://stackoverflow.com/questions/34170618/normal-equation-and-numpy-least-squares-solve-methods-difference-in-regress
                    ## note4: null space https://www.slideserve.com/marietta/kinematic-redundancy
                    ## note5: avoid joint limits; Paper Name: Clamping weighted least-norm method for the manipulator kinematic control: Avoiding joint limits
                    ## note6: constant damper; Sugihara Paper: https://www.mi.ams.eng.osaka-u.ac.jp/member/sugihara/pub/jrsj_ik.pdf
                    # strecthingcoeff = 1 / (1 + math.exp(1 / ((errnorm / self.max_rng) * 1000 + 1)))
                    # strecthingcoeff = -2*math.pow(errnorm / errnormmax, 3)+3*math.pow(errnorm / errnormmax, 2)
                    # print("stretching ", strecthingcoeff)
                    # dampercoeff = (strecthingcoeff + .1) * 1e-6  # a non-zero regulation coefficient
                    dampercoeff = 1e-3*errnorm + 1e-6  # a non-zero regulation coefficient
                    # -- lft moore-penrose inverse --
                    ## jtj = armjac.T.dot(armjac)
                    ## regulator = regcoeff*np.identity(jtj.shape[0])
                    ## jstar = np.linalg.inv(jtj+regulator).dot(armjac.T)
                    ## dq = jstar.dot(err)
                    # -- rgt moore-penrose inverse --
                    # # jjt
                    # jjt = jmat.dot(jmat.T)
                    # damper = dampercoeff * np.identity(jjt.shape[0])
                    # jsharp = jmat.T.dot(np.linalg.inv(jjt + damper))
                    # weighted jjt
                    qs_wtdiagmat = self._wln_weightmat(jntvalues_iter)
                    winv_jt = np.linalg.inv(qs_wtdiagmat).dot(jmat.T)
                    j_winv_jt = jmat.dot(winv_jt)
                    damper = dampercoeff * np.identity(j_winv_jt.shape[0])
                    jsharp = winv_jt.dot(np.linalg.inv(j_winv_jt + damper))
                    dq = .1 * jsharp.dot(err)
                    # dq = rm.regulate_angle(-math.pi, math.pi, dq)
                    # dq = Jsharp dx+(I-Jsharp J)dq0
                    dqref = (jntvalues_ref - jntvalues_iter)
                    dqref_on_ns = (np.identity(dqref.shape[0]) - jsharp.dot(jmat)).dot(dqref)
                    # dqref_on_ns = rm.regulate_angle(-math.pi, math.pi, dqref_on_ns)
                    dq_minimized = dq + dqref_on_ns
                    if toggle_debug:
                        dqbefore.append(dq)
                        dqcorrected.append(dq_minimized)
                        dqnull.append(dqref_on_ns)
                jntvalues_iter += dq_minimized  # translation problem
                # isdragged, jntvalues_iter = self.check_jntsrange_drag(jntvalues_iter)
                # print(jntvalues_iter)
                self.jlobject.fk(jnt_values=jntvalues_iter)
                # if toggle_debug:
                #     jlmgen.gensnp(jlinstance, tcp_jntid=tcp_jntid, tcp_loc_pos=tcp_loc_pos,
                #                   tcp_loc_rotmat=tcp_loc_rotmat, togglejntscs=True).reparentTo(base.render)
            errnormlast = errnorm
        if toggle_debug:
            fig = plt.figure()
            axbefore = fig.add_subplot(411)
            axbefore.set_title('Original dq')
            axnull = fig.add_subplot(412)
            axnull.set_title('dqref on Null space')
            axcorrec = fig.add_subplot(413)
            axcorrec.set_title('Minimized dq')
            axaj = fig.add_subplot(414)
            axbefore.plot(dqbefore)
            axnull.plot(dqnull)
            axcorrec.plot(dqcorrected)
            axaj.plot(ajpath)
            plt.show()
            self.jlobject.gen_stickmodel(tcp_jntid=tcp_jntid, tcp_loc_pos=tcp_loc_pos,
                                         tcp_loc_rotmat=tcp_loc_rotmat, toggle_jntscs=True).attach_to(base)
            base.run()
        self.jlobject.fk(jntvalues_bk)
        wns.warn('Failed to solve the IK, returning None.')
        return None

    def numik_rel(self, deltapos, deltarotmat, tcp_jntid=None, tcp_loc_pos=None, tcp_loc_rotmat=None):
        """
        add deltapos, deltarotmat to the current end
        :param deltapos:
        :param deltarotmat:
        :param tcp_jntid: a joint ID in the self.tgtjnts
        :param tcp_loc_pos: 1x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :param tcp_loc_rotmat: 3x3 nparray, decribed in the local frame of self.jnts[tcp_jntid], single value or list
        :return:
        author: weiwei
        date: 20170412, 20200331
        """
        tcp_globalpos, tcp_globalrotmat = self.get_gl_tcp(tcp_jntid, tcp_loc_pos, tcp_loc_rotmat)
        if isinstance(tcp_jntid, list):
            tgt_pos = []
            tgt_rotmat = []
            for i, jid in enumerate(tcp_jntid):
                tgt_pos.append(tcp_globalpos[i] + deltapos[i])
                tgt_rotmat.append(np.dot(deltarotmat, tcp_globalrotmat[i]))
            start_conf = self.jlobject.getjntvalues()
            # return numik(rjlinstance, tgt_pos, tgt_rotmat, start_conf=start_conf, tcp_jntid=tcp_jntid, tcp_loc_pos=tcp_loc_pos, tcp_loc_rotmat=tcp_loc_rotmat)
        else:
            tgt_pos = tcp_globalpos + deltapos
            tgt_rotmat = np.dot(deltarotmat, tcp_globalrotmat)
            start_conf = self.jlobject.getjntvalues()
        return self.numik(tgt_pos, tgt_rotmat, start_conf=start_conf, tcp_jntid=tcp_jntid, tcp_loc_pos=tcp_loc_pos,
                          tcp_loc_rotmat=tcp_loc_rotmat)

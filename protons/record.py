# coding=utf-8
"""
Functionality to record simulation output by means of netCDF4 files
"""
import netCDF4
import numpy as np
from simtk import unit, openmm

import protons

# Specification of attributes and variable types to be stored and read
# tuples of (name, type, unit)

# Single value attributes of ProtonDrive (states, and ncmc work are defined separately)
drive_attributes = [('naccepted', int, None), ("nrejected", int, None), ("nattempted", int, None)]
# Global variables of GHMC integrators
ghmc_global_variables = [('naccept', int, None), ('ntrials', int, None), ('work', np.float64, 'kilojoule_per_mole')]
# Context state variables
state_vars = [('total_energy', np.float64, 'kilojoule_per_mole'),
              ('kinetic_energy', np.float64, 'kilojoule_per_mole'),
              ('potential_energy', np.float64, 'kilojoule_per_mole'),
              ('temperature', np.float64, 'kelvin'), ]


def netcdf_file(filename, num_titratable_groups, ncmc_steps_per_trial, num_attempts_per_update, num_iterations=None,
                degrees_of_freedom=-1):
    """ Creates a netCDF4 file with groups and variables for ProtonDrives, State, and GHMCIntegrator

    Parameters
    ----------
    filename - str
        Name of the nc file that is to be created

    num_titratable_groups - int
        Number of titratable groups in the system
    num_attempts_per_update - int
        Number of protonation state change attempts per system update
    ncmc_steps_per_trial - int
        Number of steps per ncmc trial (1 propagation + 1 perturbation step counts as one)
    num_iterations - int, default is None
        Number of iterations, leave None for unlimited
    degrees_of_freedom - int, default = -1
        Degrees of freedom of the system. Necessary to calculate temperature.
        Can be provided for convenience if known. Otherwise, gets calculated the first time it is needed.
    Returns
    -------
    Dataset - netCDF4 dataset
    """
    ncfile = netCDF4.Dataset(filename, mode='w', format='NETCDF4')
    ncfile.degrees_of_freedom = degrees_of_freedom
    ncfile.version = protons.__version__
    ncfile.createDimension('iteration', size=num_iterations)
    ncfile.createVariable('iteration', int, ('iteration',))


    # System variable group
    system = ncfile.createGroup('State')
    for state_var, state_type, state_unit in state_vars:
        newvar = system.createVariable(state_var, state_type, ('iteration',))
        if state_unit is not None:
            newvar.unit = state_unit

    # Proton drive variable group
    proton_drive = ncfile.createGroup('ProtonDrive')
    proton_drive.createDimension('attempt', size=num_attempts_per_update)
    proton_drive.createVariable('attempt', int, ('iteration', 'attempt',))
    proton_drive.createDimension('group', size=num_titratable_groups)
    for attribute, attrtype, attrunit in drive_attributes:
        newvar = proton_drive.createVariable(attribute, attrtype, ('iteration',))
        if attrunit is not None:
            newvar.unit = attrunit

    # Titration state at each iteration, for each residue
    proton_drive.createVariable('titration_states', int, ('iteration', 'group'))
    # History of proposal information
    proton_drive.createVariable('initial_states', int, ('iteration', 'attempt', 'group'))
    proton_drive.createVariable('proposed_final_states', int, ('iteration', 'attempt', 'group'))
    proton_drive.createVariable('proposal_work', np.float64, ('iteration', 'attempt',))

    # NCMC integrator variable subgroup
    ncmc_integrator = proton_drive.createGroup('NCMCIntegrator')
    ncmc_integrator.createDimension('ncmc_step', size=ncmc_steps_per_trial)
    ncmc_integrator.createVariable('ncmc_step', int, ('iteration', 'attempt', 'ncmc_step',))
    # Work per ncmc step at each algorithm iteration
    work_per_step = ncmc_integrator.createVariable('work_per_step', np.float64, ('iteration', 'attempt', 'ncmc_step',))
    work_per_step.unit = "unitless"
    ncmc_integrator.createVariable('naccept', int, ('iteration', 'attempt', 'ncmc_step',))
    ncmc_integrator.createVariable('ntrials', int, ('iteration', 'attempt', 'ncmc_step',))

    # GHMC integrator variable group
    ghmc_integrator = ncfile.createGroup('GHMCIntegrator')
    for globvar, vartype, varunit in ghmc_global_variables:
        newvar = ghmc_integrator.createVariable(globvar, vartype, ('iteration',))
        if varunit is not None:
            newvar.unit = varunit

    return ncfile


def record_drive_data(ncfile, drive, iteration):
    """
    Store all relevant properties of a ProtonDrive type object in a netcdf dataset.

    Parameters
    ----------
    ncfile - netCDF4.Dataset
        An opened netCDF4 dataset object.
    drive - ProtonDrive object
        This function will save all relevant properties of the supplied drive
    iteration - the current iteration

    """
    # Append new iteration to the ProtonDrive variable group
    for attribute, attrtype, attrunit in drive_attributes:
        ncfile['ProtonDrive/{}'.format(attribute)][iteration] = getattr(drive, attribute)

    # Append the titration state for each group
    for titration_group_index, titration_state in enumerate(drive.titrationStates):
        ncfile['ProtonDrive/titration_states'][iteration, titration_group_index] = titration_state

    for attempt_index, attempt in enumerate(drive.last_proposal):
        ncfile['ProtonDrive/attempt'][iteration, attempt_index] = attempt_index
        for titration_group_index, titration_state in enumerate(attempt[0]):
            ncfile['ProtonDrive/initial_states'][iteration, attempt_index, titration_group_index] = titration_state

        for titration_group_index, titration_state in enumerate(attempt[1]):
            ncfile['ProtonDrive/proposed_final_states'][
                iteration, attempt_index, titration_group_index] = titration_state

        ncfile['ProtonDrive/proposal_work'][iteration, attempt_index] = attempt[2]

    # Append new iteration to the NCMC integrator variable group
    for attempt_index, attempt in enumerate(drive.ncmc_stats_per_step):
        for step_index, step in enumerate(attempt):
            ncfile['ProtonDrive/NCMCIntegrator/ncmc_step'][iteration, attempt_index, step_index] = step_index
            ncfile['ProtonDrive/NCMCIntegrator/work_per_step'][iteration, attempt_index, step_index] = step[0]
            ncfile['ProtonDrive/NCMCIntegrator/naccept'][iteration, attempt_index, step_index] = int(step[1])
            ncfile['ProtonDrive/NCMCIntegrator/ntrials'][iteration, attempt_index, step_index] = int(step[2])

    return


def record_ghmc_integrator_data(ncfile, integrator, iteration):
    """
    Store relevant properties of a GHMCIntegrator object in a netcdf dataset

    Parameters
    ----------
    ncfile - netCDF4.Dataset
        An opened netCDF4 Dataset object.
    integrator - protons.integrators.GHMCIntegrator
        Custom GHMCIntegrator class to save variables from
    iteration - the current iteration

    """
    # Append new iteration to the GHMCIntegrator variable group
    for globvar, vartype, varunit in ghmc_global_variables:
        ncfile['GHMCIntegrator/{}'.format(globvar)][iteration] = vartype(integrator.getGlobalVariableByName(globvar))


def record_state_data(ncfile, context, system, iteration):
    """
    Store state properties from a simulation Context, and System object

    Parameters
    ----------
    ncfile - netCDF4.Dataset
        An opened netCDF4 Dataset object
    context - openmm simulation Context object
        The context from which to save the state
    system - openmm simulation System object
        The simulation system
    iteration - int
        The current iteration

    """

    # See if degrees of freedom has been instantiated, if not calculate
    if ncfile.degrees_of_freedom < 0:
        ncfile.degrees_of_freedom = _calculate_degrees_of_freedom(system)

    # Extract the data from state

    state = context.getState(getEnergy=True)
    statedata = {'potential_energy': state.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole),
                 'kinetic_energy': state.getKineticEnergy().value_in_unit(unit.kilojoule_per_mole)}
    statedata['total_energy'] = statedata['potential_energy'] + statedata['kinetic_energy']
    # T = 2 * Kin / ( R * dof)
    statedata['temperature'] = (2 * statedata['kinetic_energy'] * unit.kilojoule_per_mole / (
        ncfile.degrees_of_freedom * unit.MOLAR_GAS_CONSTANT_R)).value_in_unit(unit.kelvin)

    for state_var, state_type, state_unit in state_vars:
        ncfile['State/{}'.format(state_var)][iteration] = statedata[state_var]


def _calculate_degrees_of_freedom(system):
    """
    Calculate degrees of freedom of an OpenMM system

    Based on simtk/openmm/app/statedatareporter.py

    Parameters
    ----------
    system - OpenMM simulation System

    Returns
    -------
    int - degrees of freedom
    """
    degrees_of_freedom = 0
    for i in range(system.getNumParticles()):
        # If particle is real (has mass), add 3 degrees for each coordinate
        if system.getParticleMass(i) > 0 * unit.dalton:
            degrees_of_freedom += 3
    # Every constraint removes a degree of freedom
    degrees_of_freedom -= system.getNumConstraints()
    # Adding a CMMotionRemover removes 3 degrees of freedom from the system
    if any(type(system.getForce(i)) == openmm.CMMotionRemover for i in range(system.getNumForces())):
        degrees_of_freedom -= 3

    return degrees_of_freedom


def record_all(ncfile, iteration, drive=None, integrator=None, context=None, system=None):
    """
    Save relevant properties from ProtonDrive, GHMCIntegrator, and context plus system with one function

    Parameters
    ----------

    ncfile - netCDF4.Dataset
        An opened netCDF4 Dataset object
    drive - ProtonDrive object, optional
        This function will save all relevant properties of the supplied drive
    integrator - protons.integrators.GHMCIntegrator, optional
        Custom GHMCIntegrator class to save variables from
    context - openmm simulation Context object, optional except if system is supplied
        The context from which to save the state, optional except if context is supplied
    system - openmm simulation System object
        The simulation system
    iteration - int
        The current iteration

    Returns
    -------

    """
    # Extend the iteration variable ( and dimension )
    ncfile['iteration'][iteration] = iteration
    if drive is not None:
        record_drive_data(ncfile, drive, iteration)
    if integrator is not None:
        record_ghmc_integrator_data(ncfile, integrator, iteration)
    if system is not None and context is not None:
        record_state_data(ncfile, context, system, iteration)


def _walk_netcdf_tree(top):
    """
    Recurse through a given netcdf Dataset or Group and yield children

    Parameters
    ----------
    top - top branch of a netcdf file (Group or Dataset)

    Yields
    ------
    netCDF4.Groups

    """
    values = top.groups.values()
    yield values
    for value in top.groups.values():
        for children in _walk_netcdf_tree(value):
            yield children


def display_content_structure(rootgrp):
    """
    Display the contents of a netcdf directory

    Parameters
    ----------
    rootgrp - the directory to walk through
    """
    for children in _walk_netcdf_tree(rootgrp):
        for child in children:
            print(child)
